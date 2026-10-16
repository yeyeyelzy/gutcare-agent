"""Repeatable PostgreSQL 18 integration gates for Alembic and F01 isolation."""

# Assertions intentionally keep SQL column lists and bound parameters together.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, date, datetime, timedelta
from datetime import time as local_time
from io import BytesIO
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import boto3
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from gutcare.activity.models import ActivityRecord
from gutcare.activity.service import ActivityService
from gutcare.analysis.advice import AdviceService
from gutcare.analysis.advice_models import (
    AdviceCallback,
    AdviceFeedback,
    AdviceFeedbackEvent,
    HealthAdvice,
)
from gutcare.analysis.api import router as analysis_router
from gutcare.analysis.models import AnalysisTask, TaskInputSnapshot
from gutcare.analysis.service import AnalysisService
from gutcare.app import create_app
from gutcare.auth.api import current_auth_context
from gutcare.auth.models import (
    PatientConsent,
    PatientProfile,
    RefreshSession,
    UserAccount,
)
from gutcare.auth.security import new_opaque_token, token_digest, utc_now
from gutcare.auth.service import AuthContext, AuthService
from gutcare.config import Settings
from gutcare.files.api import get_file_service
from gutcare.files.api import router as files_router
from gutcare.files.models import (
    AGENT_MEDICAL_FIELD_TYPE_PAIRS,
    MEDICAL_FIELD_TYPE_PAIRS,
    ConfirmedMedicalFact,
    FileObject,
    MedicalDocument,
    MedicalFactConflict,
    MedicalFactConflictMember,
    MedicalFieldCandidate,
    MedicalParseRequest,
)
from gutcare.files.scanner import ClamAvScanner
from gutcare.files.service import FileService
from gutcare.files.storage import S3ObjectStorage
from gutcare.medication.models import MedicationCheckin, MedicationPlan, MedicationSchedule
from gutcare.medication.service import MedicationService, materialize
from gutcare.notifications.service import NotificationService
from gutcare.notifications.worker import dispatch_batch
from gutcare.privacy.models import DeletionOperation, DeletionStep, ExportOperation, ObjectInventory
from gutcare.privacy.service import PrivacyService
from gutcare.privacy.worker import DELETE_PHASES, PrivacyWorker, scan_export_zip
from gutcare.records.models import (
    DietItem,
    DietRecord,
    RiskAlert,
    RiskRule,
    StoolRecord,
    SymptomItem,
    SymptomRecord,
)
from gutcare.records.service import RecordService
from gutcare.shared.errors import Problem, install_exception_handlers

pytestmark = pytest.mark.integration

_DATABASE_NAME = "gutcare_business_test"
_APP_ROLE = "gutcare_app"
_MIGRATOR_ROLE = "gutcare_migrator"
_METRICS_TOKEN = "integration-metrics-token-that-is-not-a-real-secret"


def _integration_urls() -> tuple[URL, URL]:
    app_raw = os.environ.get("GUTCARE_TEST_DATABASE_URL")
    migrator_raw = os.environ.get("GUTCARE_TEST_MIGRATOR_DATABASE_URL")
    if not app_raw or not migrator_raw:
        pytest.skip("Set the two test-only database URLs to run PostgreSQL integration tests.")
    app_url = make_url(app_raw)
    migrator_url = make_url(migrator_raw)
    for name, url, role in (
        ("GUTCARE_TEST_DATABASE_URL", app_url, _APP_ROLE),
        ("GUTCARE_TEST_MIGRATOR_DATABASE_URL", migrator_url, _MIGRATOR_ROLE),
    ):
        if url.database != _DATABASE_NAME or url.username != role:
            pytest.fail(f"{name} must target {_DATABASE_NAME} as {role}; refusing migration reset.")
    if (app_url.host, app_url.port, app_url.database) != (
        migrator_url.host,
        migrator_url.port,
        migrator_url.database,
    ):
        pytest.fail("Test application and migrator URLs must target the same test database.")
    return app_url, migrator_url


def _engine(url: URL, application_name: str) -> Engine:
    query = dict(url.query)
    query["application_name"] = application_name
    return create_engine(url.set(query=query), pool_pre_ping=True, pool_size=5, max_overflow=2)


def _migrate_to_head(migrator_url: URL) -> None:
    previous = os.environ.get("MIGRATOR_DATABASE_URL")
    os.environ["MIGRATOR_DATABASE_URL"] = migrator_url.render_as_string(hide_password=False)
    try:
        config = Config("alembic.ini")
        # pytest configures logging itself; avoid Alembic's fileConfig resetting
        # handlers and levels in the integration process.
        config.attributes["skip_file_config"] = True
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("MIGRATOR_DATABASE_URL", None)
        else:
            os.environ["MIGRATOR_DATABASE_URL"] = previous


def _alembic_heads() -> set[str]:
    return set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())


def test_production_readiness_checks_database_schema_and_privacy_replay(
    database: Any,
) -> None:
    app_engine, migrator_engine = database
    current_head = next(iter(_alembic_heads()))
    app_url, _ = _integration_urls()
    privacy_worker_engine = _engine(
        app_url.set(
            username="gutcare_privacy_worker",
            password=os.environ["GUTCARE_TEST_PRIVACY_WORKER_PASSWORD"],
        ),
        "gutcare-readiness-privacy-worker",
    )
    with TestClient(
        create_app(
            Settings(
                env="test",
                database_url=app_engine.url.render_as_string(hide_password=False),
            )
        )
    ) as client:
        probe_result = client.app.state.database_probe()
        assert probe_result.available and probe_result.schema_current
        assert probe_result.privacy_replay_clear
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}

        operation_id = uuid4()
        with privacy_worker_engine.begin() as db:
            db.execute(
                text("""INSERT INTO privacy.deletion_operation
                    (id, account_hash, receipt_hash, status, due_at)
                    VALUES (:id, :account_hash, :receipt_hash, 'pending', now())"""),
                {
                    "id": operation_id,
                    "account_hash": uuid4().hex + uuid4().hex,
                    "receipt_hash": uuid4().hex + uuid4().hex,
                },
            )
            db.execute(
                text("""INSERT INTO privacy.deletion_step
                    (operation_id, step_code, status)
                    VALUES (:id, 'purge_health', 'pending')"""),
                {"id": operation_id},
            )
            db.execute(
                text("""INSERT INTO privacy.object_inventory
                    (operation_id, bucket_name, source_code, status)
                    VALUES (:id, 'gutcare-test-bucket', 'file_object', 'pending')"""),
                {"id": operation_id},
            )
        try:
            not_ready = client.get("/health/ready")
            assert not_ready.status_code == 503
            assert not_ready.json() == {"status": "not_ready"}
            with privacy_worker_engine.connect() as db:
                assert (
                    db.scalar(
                        text("SELECT status FROM privacy.deletion_operation WHERE id=:id"),
                        {"id": operation_id},
                    )
                    == "pending"
                )
            with app_engine.connect() as db:
                assert db.scalar(text("SELECT privacy.replay_ready()")) is False
        finally:
            with privacy_worker_engine.begin() as db:
                db.execute(
                    text("DELETE FROM privacy.deletion_operation WHERE id=:id"),
                    {"id": operation_id},
                )
            privacy_worker_engine.dispose()
        try:
            with migrator_engine.begin() as db:
                db.execute(
                    text("UPDATE alembic_version SET version_num='0017_f13_privacy_lifecycle'")
                )
            stale_schema = client.get("/health/ready")
            assert stale_schema.status_code == 503
            with migrator_engine.begin() as db:
                db.execute(
                    text("UPDATE alembic_version SET version_num=:revision"),
                    {"revision": current_head},
                )
        finally:
            with migrator_engine.begin() as db:
                db.execute(
                    text("UPDATE alembic_version SET version_num=:revision"),
                    {"revision": current_head},
                )


def _f06_schema_fingerprint(engine: Engine) -> str:
    with engine.connect() as db:
        return db.scalar(
            text("""SELECT jsonb_build_object(
              'revision', (SELECT string_agg(version_num, ',' ORDER BY version_num)
                          FROM alembic_version),
              'relations', (SELECT jsonb_agg(jsonb_build_array(c.relname, c.relrowsecurity,
                              c.relforcerowsecurity) ORDER BY c.relname)
                           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname='health' AND c.relname IN
                             ('medication_plan','medication_schedule','medication_checkin',
                              'medication_idempotency','medication_source_ref',
                              'medication_migration_marker')),
              'policies', (SELECT jsonb_agg(jsonb_build_array(tablename, policyname, cmd,
                              qual, with_check) ORDER BY tablename, policyname)
                           FROM pg_policies WHERE schemaname='health'
                             AND tablename IN ('medication_plan','medication_schedule',
                               'medication_checkin','medication_idempotency',
                               'medication_source_ref','medication_migration_marker')),
              'constraints', (SELECT jsonb_agg(jsonb_build_array(c.relname, con.conname,
                              pg_get_constraintdef(con.oid)) ORDER BY c.relname, con.conname)
                           FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
                           JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname='health' AND c.relname IN
                             ('medication_plan','medication_source_ref',
                              'medication_migration_marker')),
              'columns', (SELECT jsonb_agg(jsonb_build_array(table_name, column_name,
                              data_type, is_nullable) ORDER BY table_name, ordinal_position)
                           FROM information_schema.columns WHERE table_schema='health'
                             AND table_name IN ('medication_plan','medication_source_ref',
                               'medication_migration_marker'))
            )::text""")
        )


@pytest.fixture(scope="module")
def database() -> Any:
    app_url, migrator_url = _integration_urls()
    app_engine = _engine(app_url, "gutcare-pg18-integration")
    migrator_engine = _engine(migrator_url, "gutcare-pg18-migrator")
    try:
        with app_engine.connect() as connection:
            database_name, current_user, version_num = connection.execute(
                text(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::integer"
                )
            ).one()
            if database_name != _DATABASE_NAME or current_user != _APP_ROLE:
                pytest.fail("Application URL did not connect as the guarded test database role.")
            if not 180000 <= version_num < 190000:
                pytest.fail("Database integration gate requires PostgreSQL 18.x.")
            row = connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            if row.rolsuper or row.rolbypassrls:
                pytest.fail("gutcare_app must be neither superuser nor BYPASSRLS.")
            uuid_value = connection.scalar(text("SELECT uuidv7()"))
            if uuid_value is None:
                pytest.fail("PostgreSQL 18 uuidv7() must be available.")
        with migrator_engine.connect() as connection:
            database_name, current_user, version_num = connection.execute(
                text(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::integer"
                )
            ).one()
            if database_name != _DATABASE_NAME or current_user != _MIGRATOR_ROLE:
                pytest.fail("Migrator URL did not connect as the guarded test migration role.")
            if not 180000 <= version_num < 190000:
                pytest.fail("Migration role must also connect to PostgreSQL 18.x.")
            row = connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            if row.rolsuper or row.rolbypassrls:
                pytest.fail("gutcare_migrator must be neither superuser nor BYPASSRLS.")
            migration_ddl = connection.scalar(
                text(
                    "SELECT has_database_privilege(current_user, current_database(), 'CREATE') "
                    "AND has_schema_privilege(current_user, 'public', 'CREATE')"
                )
            )
            if not migration_ddl:
                pytest.fail("gutcare_migrator must have the documented migration DDL privileges.")
        # This database is explicitly named and role-scoped as disposable. The
        # Alembic round trip clears only project migration schemas, never volumes.
        _migrate_to_head(migrator_url)
        with migrator_engine.connect() as connection:
            # The project schemas do not exist before the first migration, so
            # schema ACL and ownership assertions must run only after upgrade.
            app_checks = connection.execute(
                text(
                    "SELECT "
                    "EXISTS (SELECT 1 FROM pg_class AS c "
                    "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                    "WHERE n.nspname IN ('iam', 'health') "
                    "AND c.relkind IN ('r', 'p') "
                    "AND pg_get_userbyid(c.relowner) = :app_role) AS app_owns_tables, "
                    "has_database_privilege(:app_role, current_database(), 'CREATE') "
                    "OR has_schema_privilege(:app_role, 'public', 'CREATE') "
                    "OR has_schema_privilege(:app_role, 'iam', 'CREATE') "
                    "OR has_schema_privilege(:app_role, 'health', 'CREATE') "
                    "AS app_can_create_objects"
                ),
                {"app_role": _APP_ROLE},
            ).one()
            if app_checks.app_owns_tables or app_checks.app_can_create_objects:
                pytest.fail("gutcare_app must not own business tables or have DDL privileges.")

            migrator_checks = connection.execute(
                text(
                    "SELECT NOT EXISTS (SELECT 1 FROM pg_class AS c "
                    "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                    "WHERE n.nspname IN ('iam', 'health') "
                    "AND c.relkind IN ('r', 'p') "
                    "AND pg_get_userbyid(c.relowner) <> current_user)"
                )
            ).scalar_one()
            if not migrator_checks:
                pytest.fail("gutcare_migrator must own all business tables created by Alembic.")

            versions = set(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )
            heads = _alembic_heads()
            if versions != heads:
                pytest.fail(
                    f"Database revisions {versions!r} do not match Alembic heads {heads!r}."
                )
        yield app_engine, migrator_engine
    finally:
        app_engine.dispose()
        migrator_engine.dispose()


def test_operations_metrics_use_aggregate_function_only(
    database: Any, request: pytest.FixtureRequest
) -> None:
    app_engine, _ = database
    app_url, _ = _integration_urls()
    worker_engine = _engine(
        app_url.set(
            username="gutcare_privacy_worker",
            password=os.environ["GUTCARE_TEST_PRIVACY_WORKER_PASSWORD"],
        ),
        "gutcare-metrics-privacy-worker",
    )
    operation_id = uuid4()

    def cleanup() -> None:
        with worker_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM privacy.object_inventory WHERE operation_id=:id"),
                {"id": operation_id},
            )
            connection.execute(
                text("DELETE FROM privacy.deletion_operation WHERE id=:id"),
                {"id": operation_id},
            )
        worker_engine.dispose()

    request.addfinalizer(cleanup)
    account_hash = uuid4().hex + uuid4().hex
    receipt_hash = uuid4().hex + uuid4().hex
    object_key = f"metrics-check/{uuid4()}"
    with worker_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO privacy.deletion_operation "
                "(id,account_hash,receipt_hash,status,requested_at,due_at) "
                "VALUES (:id,:account,:receipt,'overdue',now()-interval '40 days',"
                "now()-interval '35 days')"
            ),
            {"id": operation_id, "account": account_hash, "receipt": receipt_hash},
        )
        connection.execute(
            text(
                "INSERT INTO privacy.object_inventory "
                "(operation_id,bucket_name,object_key,source_code,status) "
                "VALUES (:operation,'gutcare-test',:key,'file_object','pending')"
            ),
            {"operation": operation_id, "key": object_key},
        )
    with app_engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT has_function_privilege('gutcare_app', "
                "'public.gutcare_metrics_snapshot()', 'EXECUTE')"
            )
        )
        assert not connection.scalar(
            text("SELECT has_table_privilege('gutcare_app', 'privacy.object_inventory', 'SELECT')")
        )
        assert not connection.scalar(
            text(
                "SELECT has_table_privilege('gutcare_app', "
                "'integration.file_deletion_job', 'SELECT')"
            )
        )
        function_security = connection.execute(
            text(
                "SELECT pg_get_userbyid(p.proowner), p.proconfig, "
                "pg_get_function_result(p.oid) "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='public' AND p.proname='gutcare_metrics_snapshot'"
            )
        ).one()
        assert function_security[0] == _MIGRATOR_ROLE
        assert any(
            config.startswith("search_path=pg_catalog, health, integration, privacy")
            for config in (function_security[1] or [])
        )
        assert function_security[2] == (
            "TABLE(queue text, state text, item_count bigint, oldest_age_seconds bigint)"
        )
        snapshot_rows = connection.execute(
            text(
                "SELECT queue,state,item_count,oldest_age_seconds "
                "FROM public.gutcare_metrics_snapshot()"
            )
        ).all()
        privacy_inventory_row = next(
            row
            for row in snapshot_rows
            if row.queue == "privacy_inventory" and row.state == "backlog"
        )
        assert privacy_inventory_row.item_count >= 1
        assert privacy_inventory_row.oldest_age_seconds > 30 * 24 * 3600
    app = create_app(
        Settings(
            env="test",
            database_url=app_engine.url.render_as_string(hide_password=False),
            metrics_enabled=True,
            metrics_token=_METRICS_TOKEN,
        )
    )
    with app.state.database_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == _APP_ROLE
        try:
            api_snapshot = connection.execute(
                text(
                    "SELECT queue,state,item_count,oldest_age_seconds "
                    "FROM public.gutcare_metrics_snapshot()"
                )
            ).all()
        except Exception as error:
            sqlstate = getattr(getattr(error, "orig", None), "sqlstate", "unknown")
            pytest.fail(f"API engine aggregate snapshot failed with SQLSTATE {sqlstate}.")
        api_inventory_age = next(
            row.oldest_age_seconds
            for row in api_snapshot
            if row.queue == "privacy_inventory" and row.state == "backlog"
        )
        assert api_inventory_age > 30 * 24 * 3600
    captured_snapshot: list[tuple[str, str, int, float]] = []
    original_update_backlog = app.state.metrics.update_backlog

    def capture_snapshot(rows: Any) -> None:
        materialized = list(rows)
        captured_snapshot.extend(materialized)
        original_update_backlog(materialized)

    app.state.metrics.update_backlog = capture_snapshot
    response = TestClient(app).get("/ops/metrics", headers={"X-Ops-Metrics-Token": _METRICS_TOKEN})
    assert response.status_code == 200
    assert "gutcare_metrics_db_snapshot_success 1.0" in response.text
    assert "gutcare_worker_backlog" in response.text
    assert "notification_outbox" in response.text
    inventory_age_match = re.search(
        r'gutcare_worker_oldest_backlog_age_seconds\{queue="privacy_inventory"\} '
        r"([0-9.eE+-]+)",
        response.text,
    )
    assert inventory_age_match
    endpoint_inventory_row = next(
        row for row in captured_snapshot if row[0] == "privacy_inventory" and row[1] == "backlog"
    )
    assert endpoint_inventory_row[3] == api_inventory_age
    assert float(inventory_age_match.group(1)) == api_inventory_age
    assert api_inventory_age > 30 * 24 * 3600
    assert object_key not in response.text
    assert _METRICS_TOKEN not in response.text
    assert "/ops/metrics" not in app.openapi()["paths"]


def test_nfr_global_business_table_rls_and_runtime_role_matrix(database: Any) -> None:
    app_engine, _ = database
    # Exceptions are intentionally narrow, table-specific and documented in
    # docs/数据库设计方案.md §11.2: auth bootstrap data, global rules, and a
    # schema migration marker contain no patient-owned records.
    rls_exceptions = {
        ("iam", "user_account"): "email authentication identity; service-scoped, no patient rows",
        ("iam", "refresh_session"): "authentication session family; user-scoped, no patient rows",
        (
            "iam",
            "email_verification_token",
        ): "email verification bootstrap; token-hash scoped, no patient rows",
        ("safety", "risk_rule"): "global reviewed deterministic rule definitions, no patient data",
        (
            "health",
            "medication_migration_marker",
        ): "fixed-key migration safety marker, no patient dimension",
    }
    business_schemas = ("iam", "health", "analysis", "safety", "integration", "privacy")
    with app_engine.connect() as connection:
        table_rows = (
            connection.execute(
                text(
                    "SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "pg_get_userbyid(c.relowner) AS owner "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r','p') "
                    "ORDER BY n.nspname,c.relname"
                ),
                {"schemas": list(business_schemas)},
            )
            .mappings()
            .all()
        )
        violations: list[str] = []
        for row in table_rows:
            key = (row["nspname"], row["relname"])
            if key not in rls_exceptions and not (
                row["relrowsecurity"] and row["relforcerowsecurity"]
            ):
                violations.append(f"RLS/FORCE missing: {key[0]}.{key[1]}")
            if row["owner"] != "gutcare_migrator":
                violations.append(f"non-migrator owner: {key[0]}.{key[1]}={row['owner']}")
        observed = {(row["nspname"], row["relname"]) for row in table_rows}
        if not rls_exceptions.keys() <= observed:
            violations.append(
                f"stale RLS exception entries: {sorted(rls_exceptions.keys() - observed)}"
            )

        roles = (
            connection.execute(
                text(
                    "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = ANY(:roles)"
                ),
                {
                    "roles": [
                        "gutcare_app",
                        "gutcare_analysis_worker",
                        "gutcare_worker",
                        "gutcare_notification_worker",
                        "gutcare_privacy_worker",
                        "gutcare_migrator",
                    ]
                },
            )
            .mappings()
            .all()
        )
        for role in roles:
            if (
                role["rolsuper"]
                or role["rolbypassrls"]
                or role["rolcreatedb"]
                or role["rolcreaterole"]
            ):
                violations.append(f"elevated runtime/deployment role attributes: {role['rolname']}")
        if {row["rolname"] for row in roles} != {
            "gutcare_app",
            "gutcare_analysis_worker",
            "gutcare_worker",
            "gutcare_notification_worker",
            "gutcare_privacy_worker",
            "gutcare_migrator",
        }:
            violations.append("one or more required database roles are missing")

        forbidden_grants = connection.execute(
            text(
                "SELECT role_name, relation_name FROM (VALUES "
                "('gutcare_analysis_worker','health.file_object'), "
                "('gutcare_analysis_worker','health.medical_document'), "
                "('gutcare_worker','iam.user_account'), "
                "('gutcare_worker','privacy.deletion_operation'), "
                "('gutcare_notification_worker','analysis.health_advice'), "
                "('gutcare_notification_worker','health.medication_plan'), "
                "('gutcare_privacy_worker','safety.risk_rule'), "
                "('gutcare_app','privacy.deletion_step'), "
                "('gutcare_app','privacy.object_inventory')) AS expected(role_name,relation_name) "
                "WHERE has_table_privilege(role_name, relation_name, 'SELECT')"
            )
        ).all()
        violations.extend(f"overbroad SELECT grant: {row[0]}->{row[1]}" for row in forbidden_grants)

        iam_worker_grants = connection.execute(
            text(
                "SELECT role_name, relation_name FROM (VALUES "
                "('gutcare_worker','iam.user_account'), ('gutcare_worker','iam.refresh_session'), "
                "('gutcare_worker','iam.email_verification_token'), "
                "('gutcare_analysis_worker','iam.user_account'), ('gutcare_analysis_worker','iam.refresh_session'), "
                "('gutcare_analysis_worker','iam.email_verification_token'), "
                "('gutcare_notification_worker','iam.user_account'), ('gutcare_notification_worker','iam.refresh_session'), "
                "('gutcare_notification_worker','iam.email_verification_token')) AS expected(role_name,relation_name) "
                "WHERE has_table_privilege(role_name,relation_name,'SELECT') "
                "OR has_table_privilege(role_name,relation_name,'INSERT') "
                "OR has_table_privilege(role_name,relation_name,'UPDATE') "
                "OR has_table_privilege(role_name,relation_name,'DELETE')"
            )
        ).all()
        violations.extend(f"overbroad IAM grant: {row[0]}->{row[1]}" for row in iam_worker_grants)

        app_file_queue = connection.execute(
            text(
                "SELECT has_table_privilege('gutcare_app','integration.file_deletion_job','INSERT'), "
                "has_table_privilege('gutcare_app','integration.file_deletion_job','SELECT'), "
                "has_table_privilege('gutcare_app','integration.file_deletion_job','UPDATE'), "
                "has_table_privilege('gutcare_app','integration.file_deletion_job','DELETE'), "
                "has_table_privilege('gutcare_worker','integration.file_deletion_job','SELECT,INSERT,UPDATE,DELETE')"
            )
        ).one()
        if tuple(app_file_queue) != (True, False, False, False, True):
            violations.append(
                "file deletion queue privileges do not match app-insert/worker-process contract"
            )

        app_ddl = connection.scalar(
            text(
                "SELECT has_database_privilege('gutcare_app',current_database(),'CREATE') OR "
                "has_schema_privilege('gutcare_app','health','CREATE') OR "
                "has_schema_privilege('gutcare_app','iam','CREATE')"
            )
        )
        if app_ddl:
            violations.append("gutcare_app has DDL privileges")
        assert not violations, "; ".join(violations)

        # Verify the queue's WITH CHECK policy rejects an app insert for any
        # patient other than the transaction-local authenticated patient.
        authenticated_patient = uuid4()
        foreign_patient = uuid4()
        try:
            with connection.begin_nested():
                connection.execute(
                    text("SELECT set_config('app.patient_id', :patient_id, true)"),
                    {"patient_id": str(authenticated_patient)},
                )
                connection.execute(
                    text(
                        "INSERT INTO integration.file_deletion_job "
                        "(patient_id,file_object_id,bucket_name,object_key,due_at) "
                        "VALUES (:patient_id,:file_id,'test','test/object',now())"
                    ),
                    {"patient_id": str(foreign_patient), "file_id": str(uuid4())},
                )
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) != "42501":
                raise
        else:
            pytest.fail("gutcare_app RLS allowed a cross-patient file deletion job insert")


def _sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def _service(engine: Engine) -> AuthService:
    return AuthService(
        Settings(
            env="test",
            jwt_signing_key="integration-only-signing-key-000000000000000000000000",
            jwt_issuer="gutcare-business-api",
            jwt_audience="gutcare-mobile-app",
        ),
        _sessions(engine),
    )


def _seed_patient(engine: Engine, *, nickname: str = "synthetic") -> tuple[UUID, UUID]:
    user_id = uuid4()
    profile_id = uuid4()
    with _sessions(engine).begin() as db:
        db.add(
            UserAccount(
                id=user_id,
                email_ciphertext=b"synthetic-test-only",
                email_lookup_hash=hashlib.sha256(user_id.bytes).hexdigest(),
                password_hash="test-only-not-a-password-hash",
                status="active",
                failed_login_count=0,
            )
        )
        db.flush()
        db.execute(
            text("SELECT set_config('app.user_id', :value, true)"),
            {"value": str(user_id)},
        )
        db.add(
            PatientProfile(
                id=profile_id,
                user_id=user_id,
                nickname=nickname,
                birth_year=1990,
                timezone="Asia/Shanghai",
                profile_version=1,
            )
        )
        db.flush()
        db.execute(
            text("SELECT set_config('app.patient_id', :value, true)"),
            {"value": str(profile_id)},
        )
        db.add(
            PatientConsent(
                patient_id=profile_id,
                consent_type="health_data_processing",
                document_version="test-v1",
                granted=True,
                decided_at=utc_now(),
                metadata_json={"notice_summary_hash": "0" * 64},
            )
        )
    return user_id, profile_id


def _seed_refresh_family(engine: Engine, *, session_count: int = 2) -> tuple[UUID, UUID, list[str]]:
    user_id, _ = _seed_patient(engine)
    root_id = uuid4()
    now = utc_now()
    raw_tokens = [new_opaque_token() for _ in range(session_count)]
    family = [
        RefreshSession(
            id=root_id if index == 0 else uuid4(),
            family_id=root_id,
            parent_session_id=None if index == 0 else root_id,
            user_id=user_id,
            token_hash=token_digest(raw_token),
            expires_at=now + timedelta(days=2),
        )
        for index, raw_token in enumerate(raw_tokens)
    ]
    # The two-row family is only used by deletion; refresh tests seed one root.
    if session_count > 1:
        family[1].replaced_by_session_id = None
    with _sessions(engine).begin() as db:
        db.add_all(family)
    return user_id, root_id, raw_tokens


def test_migrations_round_trip_all_revisions(database: Any) -> None:
    app_engine, migrator_engine = database
    with migrator_engine.connect() as connection:
        versions = set(
            connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
        )
    assert versions == _alembic_heads()
    with migrator_engine.connect() as connection:
        policies = set(
            connection.execute(
                text(
                    "SELECT schemaname || '.' || tablename || ':' || policyname "
                    "FROM pg_policies WHERE schemaname IN ('iam', 'health')"
                )
            ).scalars()
        )
    assert "health.patient_profile:patient_profile_isolation" in policies
    assert "health.patient_consent:patient_consent_isolation" in policies
    assert "iam.account_deletion_request:account_deletion_request_owner" in policies

    previous = os.environ.get("MIGRATOR_DATABASE_URL")
    os.environ["MIGRATOR_DATABASE_URL"] = _integration_urls()[1].render_as_string(
        hide_password=False
    )
    config = Config("alembic.ini")
    config.attributes["skip_file_config"] = True
    try:
        # With no tombstones, 0010 can safely downgrade and upgrade. Seed a
        # populated 0009 schedule idempotency row and verify route-specific backfill.
        command.downgrade(config, "0009_f06_medication")
        user_id, patient_id = _seed_patient(app_engine, nickname="f06-0009-backfill")
        route_key = "f06-populated-0009-schedule"
        plan_id, schedule_id = uuid4(), uuid4()
        source_file_id, source_document_id, source_plan_id = uuid4(), uuid4(), uuid4()
        schedule_payload = {
            "local_time": local_time(8, 30),
            "timezone": "Asia/Shanghai",
            "rrule": "FREQ=DAILY",
            "valid_from": date.today() + timedelta(days=2),
            "valid_to": None,
            "enabled": True,
        }
        digest = hashlib.sha256(
            json.dumps(
                schedule_payload, sort_keys=True, separators=(",", ":"), default=str
            ).encode()
        ).hexdigest()
        route = f"POST:/medication-plans/{plan_id}/schedules"
        with app_engine.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :pid, true)"),
                {"pid": str(patient_id)},
            )
            db.execute(
                text("""INSERT INTO health.file_object
                    (id, patient_id, bucket_name, object_key, original_name, content_type,
                     size_bytes, content_sha256, sensitivity, scan_status, storage_status,
                     deleted_at)
                    VALUES (:id, :pid, 'integration', :key, 'legacy.bin',
                            'application/octet-stream',
                            1, :sha, 'medical', 'clean', 'deleted', now())"""),
                {
                    "id": source_file_id,
                    "pid": patient_id,
                    "key": f"legacy/{source_file_id}",
                    "sha": "a" * 64,
                },
            )
            db.execute(
                text("""INSERT INTO health.medical_document
                    (id, patient_id, file_object_id, document_type, processing_mode,
                     parse_status, deleted_at)
                    VALUES (:id, :pid, :file_id, 'other', 'store_only', 'not_requested', now())"""),
                {"id": source_document_id, "pid": patient_id, "file_id": source_file_id},
            )
            db.execute(
                text("""INSERT INTO health.medication_plan
                    (id, patient_id, medication_name, source_type, source_document_id,
                     confirmation_status, plan_status, record_version)
                    VALUES (:id, :pid, 'legacy-source-plan', 'medical_document', :doc_id,
                            'pending', 'discontinued', 1)"""),
                {"id": source_plan_id, "pid": patient_id, "doc_id": source_document_id},
            )
            db.execute(
                text("""INSERT INTO health.medication_plan
                    (id, patient_id, medication_name, source_type, source_document_id,
                     confirmation_status, plan_status, record_version)
                    VALUES (:id, :pid, 'legacy-seed', 'manual', NULL, 'confirmed', 'active', 1)"""),
                {"id": plan_id, "pid": patient_id},
            )
            db.execute(
                text("""INSERT INTO health.medication_schedule
                    (id, plan_id, patient_id, local_time, timezone, rrule, valid_from,
                     enabled, record_version)
                    VALUES (:id, :plan_id, :pid, '08:30', 'Asia/Shanghai', 'FREQ=DAILY',
                            :valid_from, true, 1)"""),
                {
                    "id": schedule_id,
                    "plan_id": plan_id,
                    "pid": patient_id,
                    "valid_from": schedule_payload["valid_from"],
                },
            )
            db.execute(
                text("""INSERT INTO health.medication_idempotency
                    (patient_id, route, idempotency_key, request_hash, resource_id)
                    VALUES (:pid, :route, :key, :digest, :resource_id)"""),
                {
                    "pid": patient_id,
                    "route": route,
                    "key": route_key,
                    "digest": digest,
                    "resource_id": schedule_id,
                },
            )
        command.upgrade(config, "head")
        with migrator_engine.connect() as db:
            assert db.scalar(
                text("""SELECT EXISTS (SELECT 1 FROM health.medication_migration_marker
                    WHERE marker_key = 'f06-source-tombstone-seen')""")
            )
        replay = MedicationService(_sessions(app_engine)).save_schedule(
            AuthContext(user_id=user_id, session_id=uuid4()),
            plan_id,
            None,
            None,
            schedule_payload,
            route_key,
        )
        assert replay["id"] == str(schedule_id)
        assert replay["local_time"] == "08:30:00"
        with app_engine.connect() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :pid, true)"),
                {"pid": str(patient_id)},
            )
            status = db.scalar(
                text("""SELECT response_status FROM health.medication_idempotency
                    WHERE patient_id = :pid AND route = :route AND idempotency_key = :key"""),
                {"pid": patient_id, "route": route, "key": route_key},
            )
        assert status == 201
    finally:
        if previous is None:
            os.environ.pop("MIGRATOR_DATABASE_URL", None)
        else:
            os.environ["MIGRATOR_DATABASE_URL"] = previous


def test_database_check_foreign_key_and_unique_constraints(database: Any) -> None:
    app_engine, migrator_engine = database
    user_id = uuid4()
    with pytest.raises(IntegrityError):
        with _sessions(app_engine).begin() as db:
            db.add(
                UserAccount(
                    id=user_id,
                    email_ciphertext=b"synthetic-test-only",
                    email_lookup_hash=hashlib.sha256(user_id.bytes).hexdigest(),
                    password_hash="test-only-not-a-password-hash",
                    status="invalid-status",
                    failed_login_count=0,
                )
            )

    missing_user_id = uuid4()
    with pytest.raises(IntegrityError):
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.user_id', :value, true)"),
                {"value": str(missing_user_id)},
            )
            db.add(
                PatientProfile(
                    id=uuid4(),
                    user_id=missing_user_id,
                    birth_year=1990,
                    timezone="Asia/Shanghai",
                    profile_version=1,
                )
            )

    existing_user_id, existing_profile_id = _seed_patient(app_engine)
    with pytest.raises(IntegrityError):
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.user_id', :value, true)"),
                {"value": str(existing_user_id)},
            )
            db.add(
                PatientProfile(
                    id=uuid4(),
                    user_id=existing_user_id,
                    birth_year=1990,
                    timezone="Asia/Shanghai",
                    profile_version=1,
                )
            )
    assert existing_profile_id is not None


def test_rls_patient_scope_and_transaction_local_context(database: Any) -> None:
    app_engine, migrator_engine = database
    user_a, profile_a = _seed_patient(app_engine, nickname="patient-a")
    user_b, profile_b = _seed_patient(app_engine, nickname="patient-b")

    with app_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.user_id', :value, true)"),
            {"value": str(user_a)},
        )
        connection.execute(
            text("SELECT set_config('app.patient_id', :value, true)"),
            {"value": str(profile_a)},
        )
        visible_profiles = set(
            connection.execute(text("SELECT id FROM health.patient_profile")).scalars()
        )
        visible_consents = set(
            connection.execute(text("SELECT patient_id FROM health.patient_consent")).scalars()
        )
        attempted_cross_update = connection.execute(
            text("UPDATE health.patient_profile SET nickname = 'tampered' WHERE id = :id"),
            {"id": profile_b},
        )
        assert attempted_cross_update.rowcount == 0

    assert visible_profiles == {profile_a}
    assert visible_consents == {profile_a}

    connection = app_engine.connect()
    try:
        transaction = connection.begin()
        connection.execute(
            text("SELECT set_config('app.user_id', :value, true)"),
            {"value": str(user_a)},
        )
        assert connection.scalar(text("SELECT current_setting('app.user_id', true)")) == str(user_a)
        transaction.commit()
        assert connection.scalar(text("SELECT current_setting('app.user_id', true)")) in {
            None,
            "",
        }
    finally:
        connection.close()


def test_profile_optimistic_lock_allows_only_one_stale_version_writer(database: Any) -> None:
    app_engine, _ = database
    user_id, _ = _seed_patient(app_engine, nickname="before")
    service = _service(app_engine)

    def patch(nickname: str) -> tuple[str, int | str]:
        try:
            updated = service.patch_my_profile(
                AuthContext(user_id, uuid4()),
                profile_version=1,
                changes={"nickname": nickname},
            )
            return "ok", updated.profile_version
        except Problem as error:
            return "problem", error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(patch, ("writer-a", "writer-b")))
    assert sorted(kind for kind, _ in results) == ["ok", "problem"]
    assert next(value for kind, value in results if kind == "ok") == 2
    assert next(value for kind, value in results if kind == "problem") == "RECORD_VERSION_CONFLICT"


def test_refresh_replay_under_read_committed_revokes_winning_successor(database: Any) -> None:
    app_engine, _ = database
    user_id, root_id, [old_token] = _seed_refresh_family(app_engine, session_count=1)
    service = _service(app_engine)
    blocker = app_engine.connect()
    transaction = blocker.begin()
    blocker.execute(
        text("SELECT id FROM iam.refresh_session WHERE id = :id FOR UPDATE"),
        {"id": root_id},
    )

    def refresh() -> tuple[str, str]:
        try:
            return "ok", service.refresh(old_token).refresh_token
        except Problem as error:
            return "problem", error.code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(refresh)
            second = executor.submit(refresh)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with app_engine.connect() as observer:
                    waiters = observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE application_name = 'gutcare-pg18-integration' "
                            "AND wait_event_type = 'Lock' "
                            "AND query ILIKE '%FROM iam.refresh_session%'"
                        )
                    )
                if waiters == 2:
                    break
                time.sleep(0.05)
            assert waiters == 2, "both refresh requests should block on the held family root lock"
            transaction.commit()
            results = [first.result(timeout=10), second.result(timeout=10)]
    finally:
        if transaction.is_active:
            transaction.rollback()
        blocker.close()

    successful_tokens = [value for kind, value in results if kind == "ok"]
    assert len(successful_tokens) == 1
    assert sorted(kind for kind, _ in results) == ["ok", "problem"]
    assert next(value for kind, value in results if kind == "problem") == "AUTHENTICATION_REQUIRED"
    with app_engine.connect() as connection:
        revoked_count, family_size = connection.execute(
            text(
                "SELECT count(*) FILTER (WHERE revoked_at IS NOT NULL), count(*) "
                "FROM iam.refresh_session WHERE family_id = :family_id"
            ),
            {"family_id": root_id},
        ).one()
    assert family_size == 2
    assert revoked_count == family_size
    with pytest.raises(Problem) as unusable_successor:
        service.refresh(successful_tokens[0])
    assert unusable_successor.value.code == "AUTHENTICATION_REQUIRED"


def test_account_deletion_is_atomic_and_idempotent(database: Any) -> None:
    app_engine, migrator_engine = database
    user_id, root_id, tokens = _seed_refresh_family(app_engine, session_count=2)
    service = _service(app_engine)
    trigger_name = "test_reject_account_deletion_insert"
    function_name = "test_reject_account_deletion_insert_fn"
    with migrator_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE OR REPLACE FUNCTION iam.{function_name}() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'integration rollback probe'; END $$"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON iam.account_deletion_request "
                f"FOR EACH ROW EXECUTE FUNCTION iam.{function_name}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            service.request_account_deletion(AuthContext(user_id, root_id))
        with app_engine.connect() as connection:
            status = connection.scalar(
                text("SELECT status FROM iam.user_account WHERE id = :id"), {"id": user_id}
            )
            revoked = connection.scalar(
                text(
                    "SELECT count(*) FROM iam.refresh_session "
                    "WHERE user_id = :id AND revoked_at IS NOT NULL"
                ),
                {"id": user_id},
            )
            deletion_count = connection.scalar(
                text("SELECT count(*) FROM iam.account_deletion_request WHERE user_id = :id"),
                {"id": user_id},
            )
        assert status == "active"
        assert revoked == 0
        assert deletion_count == 0
    finally:
        with migrator_engine.begin() as connection:
            connection.execute(
                text(f"DROP TRIGGER IF EXISTS {trigger_name} ON iam.account_deletion_request")
            )
            connection.execute(text(f"DROP FUNCTION IF EXISTS iam.{function_name}()"))

    deletion_id = service.request_account_deletion(AuthContext(user_id, root_id))
    assert service.request_account_deletion(AuthContext(user_id, root_id)) == deletion_id
    with app_engine.connect() as connection:
        status = connection.scalar(
            text("SELECT status FROM iam.user_account WHERE id = :id"), {"id": user_id}
        )
        session_rows = connection.execute(
            text("SELECT token_hash, revoked_at FROM iam.refresh_session WHERE user_id = :id"),
            {"id": user_id},
        ).all()
        connection.execute(
            text("SELECT set_config('app.user_id', :value, true)"),
            {"value": str(user_id)},
        )
        deletion_rows = connection.execute(
            text("SELECT id, status FROM iam.account_deletion_request WHERE user_id = :id"),
            {"id": user_id},
        ).all()
    assert status == "deactivated"
    assert len(session_rows) == 2
    assert all(row.revoked_at is not None for row in session_rows)
    assert all(row.token_hash in {token_digest(token) for token in tokens} for row in session_rows)
    assert deletion_rows == [(deletion_id, "pending")]


def test_f03_f05_postgres_rls_composite_ownership_and_rule_review_gate(database: Any) -> None:
    app_engine, migrator_engine = database
    user_a, patient_a = _seed_patient(app_engine, nickname="records-a")
    user_b, patient_b = _seed_patient(app_engine, nickname="records-b")
    service = RecordService(_sessions(app_engine))
    context_a = AuthContext(user_id=user_a, session_id=uuid4())
    context_b = AuthContext(user_id=user_b, session_id=uuid4())
    occurred_at = utc_now()
    payload = {"text_description": "synthetic meal", "items": [{"name": "synthetic food"}]}
    created = service.create(
        context_a,
        "diet-records",
        occurred_at,
        payload,
        "synthetic-stage3-key-001",
    )
    replay = service.create(
        context_a, "diet-records", occurred_at, payload, "synthetic-stage3-key-001"
    )
    assert replay["id"] == created["id"]
    with pytest.raises(Problem) as idempotency_conflict:
        service.create(
            context_a,
            "diet-records",
            occurred_at,
            {"text_description": "other"},
            "synthetic-stage3-key-001",
        )
    assert idempotency_conflict.value.status == 409
    assert service.get(context_a, "diet-records", UUID(created["id"]))["id"] == created["id"]
    with pytest.raises(Problem) as cross_patient:
        service.get(context_b, "diet-records", UUID(created["id"]))
    assert cross_patient.value.status == 404

    with app_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    "FROM pg_class WHERE oid='health.diet_record'::regclass"
                )
            )
            is True
        )
        assert (
            connection.scalar(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    "FROM pg_class WHERE oid='safety.risk_alert'::regclass"
                )
            )
            is True
        )

    created_b = service.create(
        context_b,
        "diet-records",
        occurred_at,
        {"text_description": "other synthetic meal", "items": [{"name": "other food"}]},
        "synthetic-stage3-key-patient-b",
    )
    with _sessions(app_engine)() as db:
        with db.begin():
            db.execute(
                text("SELECT set_config('app.user_id', :value, true)"),
                {"value": str(user_a)},
            )
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"),
                {"value": str(patient_a)},
            )
            visible = db.scalars(text("SELECT id FROM health.diet_record")).all()
            hidden_update = db.execute(
                text("UPDATE health.diet_record SET text_description='tampered' WHERE id=:id"),
                {"id": UUID(created_b["id"])},
            )
        assert UUID(created["id"]) in visible
        assert UUID(created_b["id"]) not in visible
        assert hidden_update.rowcount == 0
        assert db.scalar(text("SELECT current_setting('app.patient_id', true)")) in {None, ""}
        db.rollback()

        with pytest.raises(DBAPIError):
            with db.begin():
                db.execute(
                    text("SELECT set_config('app.patient_id', :value, true)"),
                    {"value": str(patient_a)},
                )
                db.execute(
                    text(
                        "INSERT INTO health.diet_record "
                        "(patient_id, occurred_at, text_description) "
                        "VALUES (:patient_id, now(), 'forbidden')"
                    ),
                    {"patient_id": patient_b},
                )
        assert db.scalar(text("SELECT current_setting('app.patient_id', true)")) in {None, ""}

    with pytest.raises(IntegrityError):
        with _sessions(migrator_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(patient_a)},
            )
            db.add(
                DietItem(
                    diet_record_id=UUID(created_b["id"]),
                    patient_id=patient_a,
                    name="cross-patient synthetic item",
                )
            )

    # A matching test-only rule must never load into production evaluation.
    with _sessions(migrator_engine).begin() as db:
        rule = RiskRule(
            rule_code="SYNTHETIC_STAGE3_ONLY",
            version=1,
            severity="attention",
            condition_json={"field": "synthetic_marker", "op": "eq", "value": True},
            message="Synthetic test message",
            recommended_action="Synthetic test action",
            review_status="approved",
            environment="test_only",
            source_refs=[],
        )
        db.add(rule)
    with pytest.raises(IntegrityError):
        with _sessions(migrator_engine).begin() as db:
            db.add(
                RiskRule(
                    rule_code="SYNTHETIC_INVALID_PRODUCTION",
                    version=1,
                    severity="attention",
                    condition_json={"field": "synthetic_marker", "op": "eq", "value": True},
                    message="Synthetic test message",
                    recommended_action="Synthetic test action",
                    review_status="approved",
                    environment="production",
                    source_refs=[],
                )
            )
    alert_count_before = service.alerts(context_a, limit=100, cursor=None)["items"]
    service.create(
        context_a,
        "stool-records",
        utc_now(),
        {"synthetic_marker": True},
        "synthetic-stage3-key-002",
    )
    alert_count_after = service.alerts(context_a, limit=100, cursor=None)["items"]
    assert alert_count_after == alert_count_before

    # A synthetic reviewed rule exercises lifecycle semantics without clinical thresholds.
    with _sessions(migrator_engine).begin() as db:
        db.add(
            RiskRule(
                rule_code="SYNTHETIC_REVIEWED_RULE",
                version=1,
                severity="attention",
                condition_json={"field": "blood_reported", "op": "eq", "value": True},
                message="Synthetic rule message",
                recommended_action="Synthetic next step",
                review_status="approved",
                environment="production",
                reviewed_by="synthetic-test-reviewer",
                reviewed_at=utc_now(),
                source_refs=["synthetic:test-only"],
                expires_at=utc_now() + timedelta(days=1),
            )
        )
    service.create(
        context_a,
        "stool-records",
        utc_now(),
        {"blood_reported": True},
        "synthetic-stage3-alert-001",
    )
    alerts = service.alerts(context_a, limit=100, cursor=None)["items"]
    generated = next(x for x in alerts if x["message"] == "Synthetic rule message")
    assert generated["status"] == "unread"
    read = service.get_alert(context_a, UUID(generated["id"]), mark_read=True)
    assert read["status"] == "read" and read["severity"] == "attention"
    assert service.get_alert(context_a, UUID(generated["id"]))["status"] == "read"

    # A distinct event with the same dangerous fact creates a distinct alert.
    service.create(
        context_a,
        "stool-records",
        utc_now(),
        {"blood_reported": True},
        "synthetic-stage3-alert-002",
    )
    alerts = service.alerts(context_a, limit=100, cursor=None)["items"]
    matching = [x for x in alerts if x["message"] == "Synthetic rule message"]
    assert len(matching) == 2
    assert {x["status"] for x in matching} == {"read", "unread"}

    symptom = service.create(
        context_a,
        "symptom-records",
        utc_now(),
        {"items": [{"symptom_code": "bloating"}]},
        "synthetic-stage3-symptom-001",
    )
    assert symptom["payload"]["symptom_status"] == "ongoing"
    changed = service.patch(
        context_a,
        "symptom-records",
        UUID(symptom["id"]),
        1,
        utc_now(),
        {"items": [{"symptom_code": "bloating"}], "symptom_status": "relieved"},
    )
    assert changed["record_version"] == 2
    history = service.symptom_status_history(context_a, UUID(symptom["id"]))
    assert history["current_status"] == "relieved"
    assert [(x["status"], x["record_version"]) for x in history["events"]] == [
        ("ongoing", 1),
        ("relieved", 2),
    ]
    with pytest.raises(Problem) as stale_symptom_patch:
        service.patch(
            context_a,
            "symptom-records",
            UUID(symptom["id"]),
            1,
            utc_now(),
            {"items": [{"symptom_code": "bloating"}], "symptom_status": "ongoing"},
        )
    assert stale_symptom_patch.value.status == 409
    with pytest.raises(Problem) as cross_patient_history:
        service.symptom_status_history(context_b, UUID(symptom["id"]))
    assert cross_patient_history.value.status == 404
    with _sessions(app_engine).begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(patient_a)},
        )
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE health.symptom_status_event SET status='ongoing' "
                        "WHERE symptom_record_id=:record_id"
                    ),
                    {"record_id": UUID(symptom["id"])},
                )

    # Text must not become a risk fact; a rule referencing a removed text field is rejected.
    with _sessions(migrator_engine).begin() as db:
        db.add(
            RiskRule(
                rule_code="SYNTHETIC_FORBIDDEN_TEXT_RULE",
                version=1,
                severity="attention",
                condition_json={"field": "notes", "op": "eq", "value": "trigger phrase"},
                message="Must never trigger from free text",
                recommended_action="Synthetic only",
                review_status="approved",
                environment="production",
                reviewed_by="synthetic-test-reviewer",
                reviewed_at=utc_now(),
                source_refs=["synthetic:test-only"],
                expires_at=utc_now() + timedelta(days=1),
            )
        )
    before = service.list(
        context_b, "stool-records", limit=100, cursor=None, since=None, until=None
    )
    with pytest.raises(Problem) as rejected_text_rule:
        service.create(
            context_b,
            "stool-records",
            utc_now(),
            {"notes": "trigger phrase"},
            "synthetic-stage3-forbidden-free-text",
        )
    assert rejected_text_rule.value.status == 503
    assert rejected_text_rule.value.code == "RISK_RULE_CONFIGURATION_ERROR"
    after = service.list(context_b, "stool-records", limit=100, cursor=None, since=None, until=None)
    assert after["items"] == before["items"]


def test_f02_real_minio_clamav_upload_document_delete_and_patient_isolation(database: Any) -> None:
    endpoint = os.environ.get("GUTCARE_TEST_S3_ENDPOINT")
    clamav_host = os.environ.get("GUTCARE_TEST_CLAMAV_HOST")
    if not endpoint or not clamav_host:
        pytest.skip("F02 integration requires private MinIO and ClamAV services.")
    app_engine, migrator_engine = database
    app_url, _ = _integration_urls()
    bucket = os.environ.get("GUTCARE_TEST_S3_BUCKET", "gutcare-files-integration")
    access_key = os.environ.get("GUTCARE_TEST_S3_ACCESS_KEY", "gutcare_test_storage")
    secret_key = os.environ.get("GUTCARE_TEST_S3_SECRET_KEY", "gutcare-test-storage-only")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )
    try:
        client.create_bucket(Bucket=bucket)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    except Exception as error:
        if "BucketAlreadyExists" not in str(error):
            raise

    worker_url = app_url.set(username="gutcare_worker", password="gutcare-test-worker-only")
    worker_engine = _engine(worker_url, "gutcare-files-worker-integration")
    service = FileService(
        _sessions(app_engine),
        S3ObjectStorage(endpoint, access_key, secret_key),
        ClamAvScanner(clamav_host, int(os.environ.get("GUTCARE_TEST_CLAMAV_PORT", "13310")), 60),
        "http://localhost",
        bucket,
        "integration-only-file-capability-secret-32chars",
        worker_sessions=_sessions(worker_engine),
    )
    user_a, patient_a = _seed_patient(app_engine, nickname="file-owner")
    user_b, patient_b = _seed_patient(app_engine, nickname="other-patient")
    context_a = AuthContext(user_a, uuid4())
    context_b = AuthContext(user_b, uuid4())

    # A valid, tiny image exercises upload, HEAD/readback, ClamAV clean, metadata,
    # authenticated cross-patient concealment, grant expiry boundary and deletion.
    from PIL import Image

    image = Image.new("RGB", (4, 4), (32, 64, 96))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    clean_bytes = buffer.getvalue()
    upload, capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="report.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-clean-01",
    )
    retry, retry_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="report.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-clean-01",
    )
    assert retry.upload_id == upload.upload_id and retry_capability == capability
    service.accept_upload(context_a, capability, clean_bytes, "image/jpeg")
    file_object = service.complete_upload(context_a, upload.upload_id)
    assert file_object.storage_status == "available"
    assert service.complete_upload(context_a, upload.upload_id).id == file_object.id
    # Enforce DB invariants directly as the worker role, bypassing service validation.
    with worker_engine.begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :id, true)"),
            {"id": str(patient_a)},
        )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text(
                        "INSERT INTO health.file_object "
                        "(id, patient_id, bucket_name, object_key, original_name, content_type, "
                        "size_bytes, content_sha256, sensitivity, scan_status, storage_status) "
                        "VALUES (:id, :patient, :bucket, :key, 'bad.jpg', 'image/jpeg', 10, "
                        ":sha, 'medical', 'pending', 'available')"
                    ),
                    {
                        "id": uuid4(),
                        "patient": patient_a,
                        "bucket": bucket,
                        "key": f"constraint/{uuid4().hex}",
                        "sha": "0" * 64,
                    },
                )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text(
                        "INSERT INTO health.upload_session "
                        "(id, patient_id, idempotency_key, request_hash, purpose, bucket_name, "
                        "object_key, capability_hash, original_name, content_type, "
                        "expected_size_bytes, file_object_id, expires_at) "
                        "VALUES (:id, :patient, :idem, :hash, 'medical_document', :bucket, :key, "
                        ":capability, 'mismatch.jpg', 'image/jpeg', 10, :file_id, "
                        "now() + interval '1 min')"
                    ),
                    {
                        "id": uuid4(),
                        "patient": patient_b,
                        "idem": f"constraint-{uuid4().hex}",
                        "hash": "1" * 64,
                        "bucket": bucket,
                        "key": f"constraint/{uuid4().hex}",
                        "capability": "2" * 64,
                        "file_id": file_object.id,
                    },
                )
    completed_retry, completed_retry_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="report.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-clean-01",
    )
    assert completed_retry.upload_id == upload.upload_id
    assert completed_retry_capability == capability
    with pytest.raises(Problem) as idempotency_conflict:
        service.create_upload(
            context_a,
            purpose="medical_document",
            file_name="different.jpg",
            content_type="image/jpeg",
            size_bytes=len(clean_bytes),
            idempotency_key="f02-integration-clean-01",
        )
    assert idempotency_conflict.value.status == 409

    doc = service.create_medical_document(
        context_a,
        file_object_id=file_object.id,
        document_type="lab_report",
        hospital_name=None,
        document_date=None,
        notes="synthetic integration",
        processing_mode="store_only",
    )
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        assert (
            db.scalar(
                text("SELECT count(*) FROM health.medical_parse_request WHERE document_id = :id"),
                {"id": doc.id},
            )
            == 0
        )
    analyze_upload, analyze_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="analyze.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-analyze-upload-01",
    )
    service.accept_upload(context_a, analyze_capability, clean_bytes, "image/jpeg")
    analyze_file = service.complete_upload(context_a, analyze_upload.upload_id)
    with pytest.raises(Problem) as ai_consent_required:
        service.create_medical_document(
            context_a,
            file_object_id=analyze_file.id,
            document_type="diagnosis_certificate",
            hospital_name=None,
            document_date=None,
            notes=None,
            processing_mode="analyze",
        )
    assert ai_consent_required.value.code == "CONSENT_REQUIRED"
    ai_consent_service = AuthService(
        Settings(
            env="test",
            jwt_signing_key="integration-only-signing-key-000000000000000000000000",
            jwt_issuer="gutcare-business-api",
            jwt_audience="gutcare-mobile-app",
            third_party_ai_policy_version="third_party_ai-v1",
            third_party_ai_summary_hash="0" * 64,
        ),
        _sessions(app_engine),
    )
    ai_consent_service.record_consent(context_a, "third_party_ai", "third_party_ai-v1", True)
    analyze_doc = service.create_medical_document(
        context_a,
        file_object_id=analyze_file.id,
        document_type="diagnosis_certificate",
        hospital_name=None,
        document_date=None,
        notes=None,
        processing_mode="analyze",
    )
    request_id = service.claim_medical_parse_request()
    assert request_id is not None
    frozen = service.get_medical_parse_inputs(request_id)
    assert frozen["document_version"] == analyze_doc.record_version
    assert frozen["content"] == clean_bytes
    candidate = {
        "field_code": "diagnosis",
        "value_type": "diagnosis",
        "value": {"text": "IBS", "certainty": "suspected"},
        "unit": None,
        "confidence": 0.8,
        "uncertainty": "synthetic test candidate",
        "source_locator": {"page": 1, "char_start": 0, "char_end": 3},
        "excerpt": "考虑 IBS",
    }
    date_candidate = {
        **candidate,
        "field_code": "document_date",
        "value_type": "date",
        "value": "2025-10-14",
        "excerpt": "2025-10-14",
    }
    recommendation_candidate = {
        **candidate,
        "field_code": "recommendation",
        "value_type": "string",
        "value": "复诊",
        "excerpt": "建议复诊",
    }
    medication_candidate = {
        **candidate,
        "field_code": "medication_name",
        "value_type": "string",
        "value": "旧药名",
        "excerpt": "旧药名",
    }
    callback_id = uuid4()
    submitted_candidates = [
        candidate,
        date_candidate,
        recommendation_candidate,
        medication_candidate,
    ]
    service.submit_medical_candidates(request_id, callback_id, submitted_candidates)
    service.submit_medical_candidates(request_id, callback_id, submitted_candidates)
    extracted_doc = service.get_medical_document(context_a, analyze_doc.id)
    assert extracted_doc.parse_outcome == "extracted" and extracted_doc.parse_reason_code is None
    candidates = service.list_medical_candidates(context_a, analyze_doc.id)
    assert len(candidates) == 4 and all(item.review_status == "pending" for item in candidates)
    empty_outcome_docs: list[Any] = []
    for index, (outcome, reason) in enumerate(
        (
            ("no_supported_facts", "no_supported_fields"),
            ("insufficient_quality", "low_quality_scan"),
        )
    ):
        empty_upload, empty_capability = service.create_upload(
            context_a,
            purpose="medical_document",
            file_name=f"empty-outcome-{index}.jpg",
            content_type="image/jpeg",
            size_bytes=len(clean_bytes),
            idempotency_key=f"f02-empty-outcome-upload-{index:02d}",
        )
        service.accept_upload(context_a, empty_capability, clean_bytes, "image/jpeg")
        empty_file = service.complete_upload(context_a, empty_upload.upload_id)
        empty_doc = service.create_medical_document(
            context_a,
            file_object_id=empty_file.id,
            document_type="lab_report",
            hospital_name=None,
            document_date=None,
            notes=None,
            processing_mode="analyze",
        )
        empty_request_id = service.claim_medical_parse_request()
        assert empty_request_id is not None
        empty_callback_id = uuid4()
        with pytest.raises(Problem) as missing_empty_outcome:
            service.submit_medical_candidates(empty_request_id, uuid4(), [])
        assert missing_empty_outcome.value.code == "VALIDATION_ERROR"
        service.submit_medical_candidates(
            empty_request_id,
            empty_callback_id,
            [],
            parse_outcome=outcome,
            reason_code=reason,
        )
        service.submit_medical_candidates(
            empty_request_id,
            empty_callback_id,
            [],
            parse_outcome=outcome,
            reason_code=reason,
        )
        empty_outcome_docs.append(empty_doc)
        with pytest.raises(Problem) as late_callback:
            service.submit_medical_candidates(
                empty_request_id,
                uuid4(),
                [],
                parse_outcome=outcome,
                reason_code=reason,
            )
        assert late_callback.value.code == "PARSE_REQUEST_STALE"
        empty_dto = service.get_medical_document(context_a, empty_doc.id)
        assert empty_dto.parse_outcome == outcome and empty_dto.parse_reason_code == reason
        assert service.list_medical_candidates(context_a, empty_doc.id) == []
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        for empty_doc in empty_outcome_docs:
            request_row = db.scalar(
                select(MedicalParseRequest).where(MedicalParseRequest.document_id == empty_doc.id)
            )
            assert request_row is not None and request_row.status == "succeeded"
            assert request_row.parse_outcome in {"no_supported_facts", "insufficient_quality"}
            assert (
                db.scalar(
                    text(
                        "SELECT count(*) FROM health.confirmed_medical_fact WHERE patient_id=:pid"
                    ),
                    {"pid": patient_a},
                )
                == 0
            )
    with _sessions(migrator_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        request_for_check = db.scalar(
            select(MedicalParseRequest).where(
                MedicalParseRequest.document_id == empty_outcome_docs[0].id
            )
        )
        assert request_for_check is not None
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE health.medical_parse_request SET parse_outcome='no_supported_facts', "
                        "parse_reason_code='low_quality_scan' WHERE id=:id"
                    ),
                    {"id": request_for_check.id},
                )
    with pytest.raises(Problem) as cross_patient_candidates:
        service.list_medical_candidates(context_b, analyze_doc.id)
    assert cross_patient_candidates.value.status == 404
    service.decide_medical_candidate(
        context_a,
        candidates[0].id,
        decision="accept",
        record_version=1,
        idempotency_key="f02-candidate-accept-01",
    )
    service.decide_medical_candidate(
        context_a,
        candidates[1].id,
        decision="correct",
        record_version=1,
        idempotency_key="f02-candidate-correct-01",
        value="2025-10-15",
    )
    service.decide_medical_candidate(
        context_a,
        candidates[3].id,
        decision="correct",
        record_version=1,
        idempotency_key="f02-medication-correct-01",
        value="更正后的药名",
    )

    def decide_recommendation(decision: str) -> str:
        try:
            service.decide_medical_candidate(
                context_a,
                candidates[2].id,
                decision=decision,
                record_version=1,
                idempotency_key=f"f02-candidate-race-{decision}",
            )
            return decision
        except Problem as error:
            assert error.status == 409
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        race_results = list(pool.map(decide_recommendation, ("accept", "reject")))
    assert sorted(race_results) in (["accept", "conflict"], ["conflict", "reject"])
    reviewed = service.list_medical_candidates(context_a, analyze_doc.id)
    reviewed_by_field = {item.field_code: item for item in reviewed}
    assert reviewed_by_field["diagnosis"].chosen_value == candidate["value"]
    assert reviewed_by_field["document_date"].chosen_value == "2025-10-15"
    assert reviewed_by_field["medication_name"].chosen_value == "更正后的药名"
    assert reviewed_by_field["medication_name"].value == "旧药名"
    assert reviewed_by_field["recommendation"].review_status in {"accepted", "rejected"}
    assert service.get_medical_document(context_a, analyze_doc.id).parse_status == "confirmed"
    service.decide_medical_candidate(
        context_a,
        candidates[0].id,
        decision="accept",
        record_version=1,
        idempotency_key="f02-candidate-accept-01",
    )
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        expected_fact_count = 3 + int(race_results[0] == "accept")
        assert (
            db.scalar(text("SELECT count(*) FROM health.confirmed_medical_fact"))
            == expected_fact_count
        )
        assert (
            db.scalar(
                text("SELECT count(*) FROM health.medical_candidate_decision"),
            )
            == 4
        )
        ledger = db.execute(
            text(
                "SELECT count(*), min(response_status), count(DISTINCT request_hash) "
                "FROM health.medical_candidate_decision_idempotency"
            )
        ).one()
        assert ledger == (4, 204, 3 + int(race_results[0] == "conflict"))

    snapshot_service = AnalysisService(_sessions(app_engine))
    snapshot_response, _ = snapshot_service.create(
        context_a,
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": None,
            "requested_to": None,
        },
        "f02-corrected-snapshot-0001",
    )
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        corrected_snapshot = db.get(TaskInputSnapshot, UUID(snapshot_response["id"]))
        assert corrected_snapshot is not None
        medical_facts = [
            row["payload"]
            for row in corrected_snapshot.snapshot_payload["records"]
            if row["record_type"] == "confirmed_medical_fact"
        ]
        corrected_medication = next(
            row for row in medical_facts if row["field_code"] == "medication_name"
        )
        assert corrected_medication["value"] == "更正后的药名"
        assert all(row["value"] != "旧药名" for row in medical_facts)
        diagnosis = next(row for row in medical_facts if row["field_code"] == "diagnosis")
        assert diagnosis["value"]["certainty"] == "suspected"

    def create_analyze_doc(file_name: str, key: str) -> Any:
        upload_row, upload_capability = service.create_upload(
            context_a,
            purpose="medical_document",
            file_name=file_name,
            content_type="image/jpeg",
            size_bytes=len(clean_bytes),
            idempotency_key=key,
        )
        service.accept_upload(context_a, upload_capability, clean_bytes, "image/jpeg")
        stored_file = service.complete_upload(context_a, upload_row.upload_id)
        return service.create_medical_document(
            context_a,
            file_object_id=stored_file.id,
            document_type="lab_report",
            hospital_name=None,
            document_date=None,
            notes=None,
            processing_mode="analyze",
        )

    # Input owns the shared advisory consent fence through MinIO read; withdrawal must wait.
    create_analyze_doc("input-race.jpg", "f02-input-race-upload-01")
    input_race_id = service.claim_medical_parse_request()
    assert input_race_id is not None
    original_storage = service._storage
    read_started, allow_read_finish = Event(), Event()

    class BlockingStorage:
        def read_object(self, bucket_name: str, object_key: str) -> bytes:
            read_started.set()
            if not allow_read_finish.wait(timeout=10):
                raise TimeoutError("blocked object read was not released")
            return original_storage.read_object(bucket_name, object_key)

    service._storage = BlockingStorage()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            input_future = pool.submit(service.get_medical_parse_inputs, input_race_id)
            assert read_started.wait(timeout=5)
            revoke_future = pool.submit(
                ai_consent_service.record_consent,
                context_a,
                "third_party_ai",
                "third_party_ai-v1",
                False,
            )
            with pytest.raises(FuturesTimeoutError):
                revoke_future.result(timeout=0.15)
            allow_read_finish.set()
            assert input_future.result(timeout=10)["content"] == clean_bytes
            revoke_future.result(timeout=10)
    finally:
        allow_read_finish.set()
        service._storage = original_storage

    ai_consent_service.record_consent(context_a, "third_party_ai", "third_party_ai-v1", True)
    create_analyze_doc("callback-race.jpg", "f02-callback-race-upload-01")
    callback_request_id = service.claim_medical_parse_request()
    assert callback_request_id is not None
    pending_doc = create_analyze_doc("claim-race.jpg", "f02-claim-race-upload-01")
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        pending_request_id = db.scalar(
            text("SELECT id FROM health.medical_parse_request WHERE document_id = :id"),
            {"id": pending_doc.id},
        )
    assert pending_request_id is not None
    callback_gate = Event()

    def race_claim() -> UUID | None:
        assert callback_gate.wait(timeout=5)
        return service.claim_medical_parse_request()

    def race_callback() -> str:
        assert callback_gate.wait(timeout=5)
        try:
            service.submit_medical_candidates(callback_request_id, uuid4(), [candidate])
            return "submitted"
        except Problem as error:
            assert error.status in {409}
            return "rejected"

    def race_revoke() -> None:
        assert callback_gate.wait(timeout=5)
        ai_consent_service.record_consent(context_a, "third_party_ai", "third_party_ai-v1", False)

    with ThreadPoolExecutor(max_workers=3) as pool:
        claim_future = pool.submit(race_claim)
        callback_future = pool.submit(race_callback)
        revoke_future = pool.submit(race_revoke)
        callback_gate.set()
        claimed_during_revoke = claim_future.result(timeout=10)
        callback_outcome = callback_future.result(timeout=10)
        revoke_future.result(timeout=10)
    assert callback_outcome in {"submitted", "rejected"}
    assert claimed_during_revoke in {None, pending_request_id}

    # After withdrawal commits, input must reject before touching object storage.
    class CountingStorage:
        def __init__(self, wrapped: Any) -> None:
            self.wrapped = wrapped
            self.reads = 0

        def read_object(self, bucket_name: str, object_key: str) -> bytes:
            self.reads += 1
            return self.wrapped.read_object(bucket_name, object_key)

    counting_storage = CountingStorage(original_storage)
    service._storage = counting_storage
    try:
        for revoked_request_id in (callback_request_id, input_race_id):
            with pytest.raises(Problem):
                service.get_medical_parse_inputs(revoked_request_id)
    finally:
        service._storage = original_storage
    assert counting_storage.reads == 0
    for operation in (
        lambda: service.submit_medical_candidates(callback_request_id, uuid4(), [candidate]),
        lambda: service.fail_medical_parse_request(callback_request_id, uuid4(), "agent_error"),
        lambda: service.get_medical_parse_inputs(input_race_id),
    ):
        with pytest.raises(Problem):
            operation()
    assert service.claim_medical_parse_request() is None
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        request_ids = [input_race_id, callback_request_id, pending_request_id]
        statuses = db.execute(
            text("SELECT id, status FROM health.medical_parse_request WHERE id = ANY(:ids)"),
            {"ids": request_ids},
        ).all()
        assert all(status == "invalidated" for _, status in statuses)
        candidate_rows = db.execute(
            text(
                "SELECT excerpt, source_locator, review_status "
                "FROM health.medical_field_candidate WHERE request_id = :id"
            ),
            {"id": callback_request_id},
        ).all()
        assert all(row == (None, None, "invalidated") for row in candidate_rows)
        facts_after_revoke = db.scalar(
            text(
                "SELECT count(*) FROM health.confirmed_medical_fact fact "
                "JOIN health.medical_field_candidate candidate "
                "ON candidate.id = fact.candidate_id WHERE candidate.request_id = :id"
            ),
            {"id": callback_request_id},
        )
        assert facts_after_revoke == 0

    def candidate_write_counts() -> tuple[int, int, int]:
        with app_engine.connect() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :pid, true)"),
                {"pid": str(patient_a)},
            )
            decisions = db.scalar(text("SELECT count(*) FROM health.medical_candidate_decision"))
            facts = db.scalar(text("SELECT count(*) FROM health.confirmed_medical_fact"))
            ledger = db.scalar(
                text("SELECT count(*) FROM health.medical_candidate_decision_idempotency")
            )
            assert decisions is not None and facts is not None and ledger is not None
            return decisions, facts, ledger

    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        linked_request = db.execute(
            text(
                "SELECT patient_id, document_id, file_object_id, status "
                "FROM health.medical_parse_request WHERE id = :id"
            ),
            {"id": request_id},
        ).one()
        assert linked_request == (patient_a, analyze_doc.id, analyze_file.id, "succeeded")
    service.delete_medical_document(context_a, analyze_doc.id)
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        redacted = db.execute(
            text(
                "SELECT excerpt, source_locator, review_status "
                "FROM health.medical_field_candidate WHERE id = :id"
            ),
            {"id": candidates[0].id},
        ).one()
        assert redacted == (None, None, "invalidated")
        parse_source = db.execute(
            text(
                "SELECT document_id, file_object_id, status, parse_outcome, parse_reason_code "
                "FROM health.medical_parse_request WHERE id = :id"
            ),
            {"id": request_id},
        ).one()
        assert parse_source == (None, None, "invalidated", "extracted", None)
        redacted_candidates = db.execute(
            text(
                "SELECT excerpt, source_locator, review_status "
                "FROM health.medical_field_candidate WHERE request_id = :request_id"
            ),
            {"request_id": request_id},
        ).all()
        assert len(redacted_candidates) == 4
        assert all(row == (None, None, "invalidated") for row in redacted_candidates)
    counts_before_replay = candidate_write_counts()
    assert counts_before_replay == (4, expected_fact_count, 4)

    decision_app = FastAPI()
    install_exception_handlers(decision_app)
    decision_app.include_router(files_router)
    decision_app.dependency_overrides[current_auth_context] = lambda: context_a
    decision_app.dependency_overrides[get_file_service] = lambda: service
    with TestClient(decision_app) as api_client:
        replay = api_client.post(
            f"/api/v1/medical-field-candidates/{candidates[0].id}/decision",
            headers={"Idempotency-Key": "f02-candidate-accept-01"},
            json={"decision": "accept", "record_version": 1},
        )
        assert replay.status_code == 204 and replay.content == b""
        assert candidate_write_counts() == counts_before_replay

        same_key_different_action = api_client.post(
            f"/api/v1/medical-field-candidates/{candidates[0].id}/decision",
            headers={"Idempotency-Key": "f02-candidate-accept-01"},
            json={"decision": "reject", "record_version": 1},
        )
        assert same_key_different_action.status_code == 409
        assert candidate_write_counts() == counts_before_replay

        same_key_different_candidate = api_client.post(
            f"/api/v1/medical-field-candidates/{candidates[1].id}/decision",
            headers={"Idempotency-Key": "f02-candidate-accept-01"},
            json={"decision": "accept", "record_version": 1},
        )
        assert same_key_different_candidate.status_code == 409
        assert candidate_write_counts() == counts_before_replay

    with worker_engine.connect() as db:
        worker_profile_update = db.execute(
            text(
                "SELECT has_table_privilege(current_user, 'health.patient_profile', 'UPDATE'), "
                "has_any_column_privilege(current_user, 'health.patient_profile', 'UPDATE')"
            )
        ).one()
        assert worker_profile_update == (False, False)

    with app_engine.connect() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :pid, true)"),
            {"pid": str(patient_a)},
        )
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text(
                        "INSERT INTO health.medical_candidate_decision_idempotency "
                        "(patient_id, candidate_id, idempotency_key, request_hash) "
                        "VALUES (:patient_id, :candidate_id, :key, :request_hash)"
                    ),
                    {
                        "patient_id": patient_b,
                        "candidate_id": candidates[0].id,
                        "key": "f02-cross-patient-rls-01",
                        "request_hash": "0" * 64,
                    },
                )
    with migrator_engine.connect() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :pid, true)"),
            {"pid": str(patient_b)},
        )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text(
                        "INSERT INTO health.medical_candidate_decision_idempotency "
                        "(patient_id, candidate_id, idempotency_key, request_hash) "
                        "VALUES (:patient_id, :candidate_id, :key, :request_hash)"
                    ),
                    {
                        "patient_id": patient_b,
                        "candidate_id": candidates[0].id,
                        "key": "f02-cross-patient-fk-01",
                        "request_hash": "1" * 64,
                    },
                )
    assert candidate_write_counts() == counts_before_replay

    with pytest.raises(Problem) as late_callback:
        service.submit_medical_candidates(request_id, uuid4(), [candidate])
    assert late_callback.value.status == 409
    medication = MedicationService(_sessions(app_engine))
    medication_context = AuthContext(user_a, uuid4())
    source_plan_payload = {
        "medication_name": "synthetic-source-plan",
        "source_type": "medical_document",
        "source_document_id": doc.id,
        "dosage_text": None,
        "route_code": None,
        "start_date": date.today(),
        "end_date": None,
    }
    source_idempotency_key = "f06-source-delete-0001"
    medication_plan = medication.create_plan(
        medication_context, source_plan_payload, source_idempotency_key
    )
    with pytest.raises(Problem) as concealed:
        service.get_medical_document(context_b, doc.id)
    assert concealed.value.status == 404
    grant = service.create_download_grant(context_a, file_object.id)
    token = grant.download_url.rsplit("/", 1)[-1]
    assert service.download_by_capability(token)[0] == clean_bytes
    service.delete_medical_document(context_a, doc.id)
    retained_plan = medication.get_plan(medication_context, UUID(medication_plan["id"]))
    assert retained_plan["source_deleted"] is True
    assert retained_plan["source_document_id"] is None
    assert str(doc.id) not in str(retained_plan)
    deleted_replay = medication.create_plan(
        medication_context, source_plan_payload, source_idempotency_key
    )
    assert deleted_replay["source_deleted"] is True
    assert deleted_replay["source_document_id"] is None
    assert str(doc.id) not in str(deleted_replay)
    with app_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_a)})
        stored_snapshot = db.scalar(
            text("""SELECT response_snapshot FROM health.medication_idempotency
                WHERE patient_id = :pid AND route = 'POST:/medication-plans'
                  AND idempotency_key = :key"""),
            {"pid": patient_a, "key": source_idempotency_key},
        )
        assert stored_snapshot["source_document_id"] is None
        assert stored_snapshot["source_deleted"] is True
        source_ref_id = db.scalar(
            text("SELECT source_ref_id FROM health.medication_plan WHERE id = :id"),
            {"id": UUID(medication_plan["id"])},
        )
    with pytest.raises(IntegrityError):
        with app_engine.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(patient_b)}
            )
            db.execute(
                text("""INSERT INTO health.medication_plan
              (patient_id, medication_name, source_type, source_ref_id,
               confirmation_status, plan_status, record_version)
              VALUES (:patient_id, 'forged', 'medical_document', :source_ref_id,
                      'pending', 'discontinued', 1)"""),
                {"patient_id": patient_b, "source_ref_id": source_ref_id},
            )
    with worker_engine.begin() as db:
        due_at = db.scalar(
            text("SELECT due_at FROM integration.file_deletion_job WHERE file_object_id = :id"),
            {"id": file_object.id},
        )
        assert due_at is not None
        assert timedelta(days=6, hours=23) < due_at - utc_now() <= timedelta(days=7, minutes=1)
    with pytest.raises(Problem) as hidden_after_delete:
        service.create_download_grant(context_a, file_object.id)
    assert hidden_after_delete.value.status == 404
    with worker_engine.begin() as db:
        db.execute(
            text(
                "UPDATE integration.file_deletion_job "
                "SET due_at = now(), status = 'processing', locked_at = now() "
                "WHERE file_object_id = :id"
            ),
            {"id": file_object.id},
        )
    assert service.process_due_deletion_jobs() == 0
    with worker_engine.connect() as db:
        job_id, deleted_object_key = db.execute(
            text(
                "SELECT id, object_key FROM integration.file_deletion_job "
                "WHERE file_object_id = :id"
            ),
            {"id": file_object.id},
        ).one()
    assert client.head_object(Bucket=bucket, Key=deleted_object_key)
    with worker_engine.begin() as db:
        db.execute(
            text(
                "UPDATE integration.file_deletion_job SET locked_at = now() - interval '6 minutes' "
                "WHERE id = :id"
            ),
            {"id": job_id},
        )
    assert service.process_due_deletion_jobs() == 1
    with worker_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, false)"), {"id": str(patient_a)})
        assert (
            db.scalar(
                text("SELECT count(*) FROM health.file_object WHERE id = :id"),
                {"id": file_object.id},
            )
            == 0
        )
        assert (
            db.scalar(
                text("SELECT count(*) FROM health.medical_document WHERE id = :id"),
                {"id": doc.id},
            )
            == 0
        )

    previous_migrator_url = os.environ.get("MIGRATOR_DATABASE_URL")
    os.environ["MIGRATOR_DATABASE_URL"] = _integration_urls()[1].render_as_string(
        hide_password=False
    )
    downgrade_config = Config("alembic.ini")
    downgrade_config.attributes["skip_file_config"] = True
    fingerprint_before = _f06_schema_fingerprint(migrator_engine)
    with migrator_engine.connect() as db:
        assert db.scalar(
            text("""SELECT EXISTS (SELECT 1 FROM health.medication_migration_marker
                WHERE marker_key = 'f06-source-tombstone-seen')""")
        )
    try:
        with pytest.raises(RuntimeError, match="forward-only"):
            command.downgrade(downgrade_config, "0009_f06_medication")
    finally:
        if previous_migrator_url is None:
            os.environ.pop("MIGRATOR_DATABASE_URL", None)
        else:
            os.environ["MIGRATOR_DATABASE_URL"] = previous_migrator_url
    assert _f06_schema_fingerprint(migrator_engine) == fingerprint_before
    with migrator_engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == next(
            iter(_alembic_heads())
        )
    with app_engine.connect() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :pid, false)"), {"pid": str(patient_a)}
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM health.medication_source_ref "
                    "WHERE source_deleted_at IS NOT NULL"
                )
            )
            >= 1
        )
    assert medication.get_plan(medication_context, UUID(medication_plan["id"]))["source_deleted"]

    # Verify that the configured production scanner detects the canonical EICAR
    # sample over the real INSTREAM protocol; placing EICAR in JPEG metadata is
    # intentionally not used because ClamAV treats that payload as image data.
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    assert service._scanner.scan(eicar) is False

    # Scanner outage must fail closed: completion returns RFC 9457 503 and must
    # never create an available file object, even when object storage is healthy.
    unavailable_upload, unavailable_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="scanner-outage.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-scanner-down-01",
    )
    service.accept_upload(context_a, unavailable_capability, clean_bytes, "image/jpeg")

    class UnavailableScanner:
        def scan(self, _content: bytes) -> bool:
            from gutcare.files.scanner import ScannerUnavailable

            raise ScannerUnavailable("simulated clamd socket failure")

    working_scanner = service._scanner
    service._scanner = UnavailableScanner()
    try:
        with pytest.raises(Problem) as scanner_error:
            service.complete_upload(context_a, unavailable_upload.upload_id)
    finally:
        service._scanner = working_scanner
    assert scanner_error.value.status == 503
    assert scanner_error.value.code == "MALWARE_SCANNER_UNAVAILABLE"
    with worker_engine.connect() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, false)"), {"id": str(patient_a)})
        assert (
            db.scalar(
                text("SELECT status FROM health.upload_session WHERE id = :id"),
                {"id": unavailable_upload.upload_id},
            )
            == "failed"
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM health.file_object WHERE object_key = ("
                    "SELECT object_key FROM health.upload_session WHERE id = :id)"
                ),
                {"id": unavailable_upload.upload_id},
            )
            == 0
        )

    # Expired staged uploads are transitioned once and receive durable cleanup work.
    stale_upload, stale_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="staged.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-stale-01",
    )
    service.accept_upload(context_a, stale_capability, clean_bytes, "image/jpeg")
    with worker_engine.begin() as db:
        db.execute(
            text(
                "UPDATE health.upload_session SET expires_at = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": stale_upload.upload_id},
        )
    assert service.reap_expired_upload_sessions() == 1
    expired_retry, expired_retry_capability = service.create_upload(
        context_a,
        purpose="medical_document",
        file_name="staged.jpg",
        content_type="image/jpeg",
        size_bytes=len(clean_bytes),
        idempotency_key="f02-integration-stale-01",
    )
    assert expired_retry.upload_id == stale_upload.upload_id
    assert expired_retry_capability == stale_capability
    with worker_engine.connect() as db:
        assert (
            db.scalar(
                text("SELECT status FROM health.upload_session WHERE id = :id"),
                {"id": stale_upload.upload_id},
            )
            == "expired"
        )
        cleanup_id, stale_object_key = db.execute(
            text(
                "SELECT j.id, j.object_key FROM integration.file_orphan_cleanup_job j "
                "WHERE object_key = (SELECT object_key FROM health.upload_session WHERE id = :id)"
            ),
            {"id": stale_upload.upload_id},
        ).one()
    assert cleanup_id is not None
    original_storage = service._storage

    class FailOnceDeleteStorage:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate
            self.fail = True

        def __getattr__(self, name: str) -> Any:
            return getattr(self.delegate, name)

        def delete_object(self, delete_bucket: str, object_key: str) -> None:
            if self.fail:
                self.fail = False
                raise RuntimeError("simulated transient object deletion failure")
            self.delegate.delete_object(delete_bucket, object_key)

    service._storage = FailOnceDeleteStorage(original_storage)
    assert service.process_due_orphan_cleanups() == 0
    with worker_engine.begin() as db:
        attempts = db.scalar(
            text("SELECT attempts FROM integration.file_orphan_cleanup_job WHERE id = :id"),
            {"id": cleanup_id},
        )
        assert attempts == 1
        db.execute(
            text("UPDATE integration.file_orphan_cleanup_job SET due_at = now() WHERE id = :id"),
            {"id": cleanup_id},
        )
    assert service.process_due_orphan_cleanups() == 1
    service._storage = original_storage
    with pytest.raises(client.exceptions.ClientError):
        client.head_object(Bucket=bucket, Key=stale_object_key)
    with worker_engine.connect() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM integration.file_orphan_cleanup_job WHERE id = :id"),
                {"id": cleanup_id},
            )
            == 0
        )
    worker_engine.dispose()


def test_f02_a07_conservative_lab_conflicts_and_snapshot(database: Any) -> None:
    app_engine, _ = database
    user, patient = _seed_patient(engine := app_engine, nickname="a07-conflicts")
    _other_user, other_patient = _seed_patient(engine, nickname="a07-other")
    sessions = _sessions(app_engine)
    integration_bucket = os.environ.get("GUTCARE_TEST_S3_BUCKET", "gutcare-files-integration")
    service = FileService(sessions, None, None, "http://localhost", "unused", "a" * 40)
    context = AuthContext(user, uuid4())

    def add_report(
        result: Any, report_date: date, name: str, unit: str | None = "mg/L"
    ) -> tuple[UUID, UUID]:
        file_id, document_id, request_id = uuid4(), uuid4(), uuid4()
        item_candidate_id, result_candidate_id = uuid4(), uuid4()
        item_fact_id, result_fact_id = uuid4(), uuid4()
        with sessions.begin() as db:
            db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
            db.add(
                FileObject(
                    id=file_id,
                    patient_id=patient,
                    bucket_name=integration_bucket,
                    object_key=f"{file_id}/report",
                    original_name=name,
                    content_type="application/pdf",
                    size_bytes=10,
                    content_sha256="1" * 64,
                    sensitivity="medical",
                    scan_status="clean",
                    storage_status="available",
                )
            )
            db.flush()
            db.add(
                MedicalDocument(
                    id=document_id,
                    patient_id=patient,
                    file_object_id=file_id,
                    document_type="lab_report",
                    document_date=report_date,
                    processing_mode="analyze",
                    parse_status="confirmed",
                    parse_outcome="extracted",
                    record_version=1,
                )
            )
            db.flush()
            db.add(
                MedicalParseRequest(
                    id=request_id,
                    patient_id=patient,
                    document_id=document_id,
                    file_object_id=file_id,
                    record_version=1,
                    status="succeeded",
                    parse_outcome="extracted",
                )
            )
            db.flush()
            item_candidate = MedicalFieldCandidate(
                id=item_candidate_id,
                patient_id=patient,
                request_id=request_id,
                field_code="test_item",
                value_type="string",
                value=" CRP ",
                unit=None,
                source_locator={"page": 1},
                excerpt="CRP",
                review_status="accepted",
                record_version=2,
            )
            result_candidate = MedicalFieldCandidate(
                id=result_candidate_id,
                patient_id=patient,
                request_id=request_id,
                field_code="test_result",
                value_type="object",
                value={"result": result, "unit": unit},
                unit=unit,
                source_locator={"page": 1},
                excerpt="result",
                review_status="accepted",
                record_version=2,
            )
            db.add_all([item_candidate, result_candidate])
            db.flush()
            db.add_all(
                [
                    ConfirmedMedicalFact(
                        id=item_fact_id,
                        patient_id=patient,
                        candidate_id=item_candidate_id,
                        field_code="test_item",
                        value_type="string",
                        value="CRP",
                        fact_status="active",
                    ),
                    ConfirmedMedicalFact(
                        id=result_fact_id,
                        patient_id=patient,
                        candidate_id=result_candidate_id,
                        field_code="test_result",
                        value_type="object",
                        value={"result": result, "unit": unit},
                        unit=unit,
                        fact_status="active",
                    ),
                ]
            )
        return document_id, file_id

    # Four reports on one date (including a repeated value) must coalesce into
    # one conflict with every source, not produce pairwise conflict records.
    source_docs = [
        add_report(value, date(2026, 10, 1), f"same-day-{value}-{index}.pdf")
        for index, value in enumerate((5, 8, 9, 8))
    ]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        candidate_id = db.scalar(
            select(MedicalFieldCandidate.id)
            .where(
                MedicalFieldCandidate.patient_id == patient,
                MedicalFieldCandidate.field_code == "test_result",
            )
            .order_by(MedicalFieldCandidate.created_at)
            .limit(1)
        )
        assert candidate_id is not None
        for field_code, value_type in MEDICAL_FIELD_TYPE_PAIRS.items():
            db.execute(
                text(
                    "UPDATE health.medical_field_candidate SET field_code=:field, value_type=:kind WHERE id=:id"
                ),
                {"field": field_code, "kind": value_type, "id": candidate_id},
            )
        assert "weight_kg" not in AGENT_MEDICAL_FIELD_TYPE_PAIRS
        db.execute(
            text(
                "UPDATE health.medical_field_candidate SET field_code='test_result', value_type='object' WHERE id=:id"
            ),
            {"id": candidate_id},
        )
        for field_code, value_type in (("diagnosis", "object"), ("test_result", "string")):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(
                        text(
                            "UPDATE health.medical_field_candidate SET field_code=:field, value_type=:kind WHERE id=:id"
                        ),
                        {"field": field_code, "kind": value_type, "id": candidate_id},
                    )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE health.medical_field_candidate SET field_code='diagnosis' WHERE id=:id"
                    ),
                    {"id": candidate_id},
                )
    # Same value on another date is a trend, never a conflict.
    add_report(8, date(2026, 10, 2), "later-same-value.pdf")
    # Decimal-equivalent result encodings and normalized units do not conflict.
    add_report(5, date(2026, 11, 3), "decimal-int.pdf", "mg/L")
    add_report(5.0, date(2026, 11, 3), "decimal-float.pdf", " MG/L ")
    add_report("5.00", date(2026, 11, 3), "decimal-string.pdf", "ｍｇ／Ｌ")
    # Missing units only compare with missing units; a known unit is a separate group.
    add_report(5, date(2026, 11, 4), "missing-unit.pdf", None)
    add_report(8, date(2026, 11, 4), "known-unit.pdf", "mg/L")
    barrier = Barrier(2)

    def reconcile() -> None:
        barrier.wait()
        with sessions.begin() as db:
            db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
            FileService._reconcile_medical_conflicts(db, patient)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _n: reconcile(), range(2)))
    conflicts = service.list_medical_fact_conflicts(context)
    assert len(conflicts) == 1
    conflict_id = UUID(conflicts[0]["id"])
    detail = service.get_medical_fact_conflict(context, conflict_id)
    assert len(detail["members"]) == 8
    assert service.list_medical_fact_conflicts(AuthContext(_other_user, uuid4())) == []
    with pytest.raises(Problem) as hidden:
        service.get_medical_fact_conflict(AuthContext(_other_user, uuid4()), conflict_id)
    assert hidden.value.status == 404

    with sessions() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        snapshot = AnalysisService._snapshot(db, patient, None, None)
    assert sum(row["record_type"] == "medical_fact_conflict" for row in snapshot["records"]) == 1
    assert not any(
        row["record_type"] == "confirmed_medical_fact"
        and row["record_id"] in {member["fact_id"] for member in detail["members"]}
        for row in snapshot["records"]
    )
    resolved = service.resolve_medical_fact_conflict(
        context, conflict_id, record_version=1, idempotency_key="a07-keep-both-001"
    )
    replay = service.resolve_medical_fact_conflict(
        context, conflict_id, record_version=1, idempotency_key="a07-keep-both-001"
    )
    assert resolved == replay and resolved["status"] == "resolved"
    with pytest.raises(Problem) as reused:
        service.resolve_medical_fact_conflict(
            context, conflict_id, record_version=2, idempotency_key="a07-keep-both-001"
        )
    assert reused.value.code == "IDEMPOTENCY_CONFLICT"
    with sessions() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        assert (
            db.scalar(
                select(func.count())
                .select_from(MedicalFactConflictMember)
                .where(MedicalFactConflictMember.conflict_id == conflict_id)
            )
            == 8
        )

    # A second independent pair with identical same-day values does not conflict.
    same_docs = [add_report(12, date(2026, 11, 1), f"same-value-{index}.pdf") for index in range(2)]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    assert len(service.list_medical_fact_conflicts(context)) == 0
    true_difference = [
        add_report(5, date(2026, 11, 5), "different-5.pdf"),
        add_report("5.01", date(2026, 11, 5), "different-5-01.pdf"),
    ]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    assert len(service.list_medical_fact_conflicts(context)) == 1
    service.delete_medical_document(context, true_difference[0][0])
    assert service.list_medical_fact_conflicts(context) == []
    precise_difference = [
        add_report("1.0000000000000000000000000001", date(2026, 11, 6), "precise-1.pdf"),
        add_report("1.0000000000000000000000000002", date(2026, 11, 6), "precise-2.pdf"),
    ]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    assert len(service.list_medical_fact_conflicts(context)) == 1
    service.delete_medical_document(context, precise_difference[0][0])
    huge_exponent = [
        add_report("1e999999999", date(2026, 11, 7), "huge-exponent-1.pdf"),
        add_report("2e999999999", date(2026, 11, 7), "huge-exponent-2.pdf"),
    ]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    assert len(service.list_medical_fact_conflicts(context)) == 1
    service.delete_medical_document(context, huge_exponent[0][0])

    delete_doc, _delete_file = add_report(10, date(2026, 10, 1), "delete-source.pdf")
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    open_after_new_source = service.list_medical_fact_conflicts(context)
    assert len(open_after_new_source) == 1
    stable_conflict_id = UUID(open_after_new_source[0]["id"])
    assert stable_conflict_id == conflict_id
    assert open_after_new_source[0]["status"] == "open"
    assert open_after_new_source[0]["record_version"] == 3
    # Moving one source date invalidates the old group and reconstructs conflict
    # membership at the new effective date, without changing the confirmed facts.
    date_move_docs = [
        add_report(20, date(2026, 12, 1), "date-move-20.pdf"),
        add_report(21, date(2026, 12, 1), "date-move-21.pdf"),
    ]
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    date_move_conflict = next(
        row
        for row in service.list_medical_fact_conflicts(context)
        if row["record_version"] == 1 and row["id"] != str(stable_conflict_id)
    )
    old_date_conflict_id = UUID(date_move_conflict["id"])
    patched_doc = date_move_docs[0][0]
    service.patch_medical_document(
        context,
        patched_doc,
        record_version=1,
        changes={"document_date": date(2026, 12, 2)},
    )
    assert all(
        row["id"] != str(old_date_conflict_id)
        for row in service.list_medical_fact_conflicts(context)
    )
    invalidated_date_conflict = service.get_medical_fact_conflict(context, old_date_conflict_id)
    assert invalidated_date_conflict["status"] == "invalidated"
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    update(MedicalFactConflict)
                    .where(MedicalFactConflict.id == old_date_conflict_id)
                    .values(
                        resolution="keep_both",
                        resolution_key="a07-invalid-state-shape",
                        request_hash="a" * 64,
                        resolved_at=datetime.now(UTC),
                    )
                )
    new_date_doc = add_report(22, date(2026, 12, 2), "date-move-new-group.pdf")
    with sessions.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        FileService._reconcile_medical_conflicts(db, patient)
    new_date_conflict = next(
        row
        for row in service.list_medical_fact_conflicts(context)
        if row["id"] != str(stable_conflict_id)
    )
    new_date_detail = service.get_medical_fact_conflict(context, UUID(new_date_conflict["id"]))
    assert new_date_detail["status"] == "open"
    assert {member["source_document_id"] for member in new_date_detail["members"]} == {
        str(patched_doc),
        str(new_date_doc[0]),
    }
    service.delete_medical_document(context, new_date_doc[0])
    race_barrier = Barrier(2)

    def race_resolve() -> str:
        race_barrier.wait()
        try:
            result = service.resolve_medical_fact_conflict(
                context,
                stable_conflict_id,
                record_version=open_after_new_source[0]["record_version"],
                idempotency_key="a07-delete-resolve-race",
            )
            return result["status"]
        except Problem as exc:
            return exc.code

    def race_delete() -> str:
        race_barrier.wait()
        service.delete_medical_document(context, delete_doc)
        return "deleted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        race_results = list(pool.map(lambda fn: fn(), (race_resolve, race_delete)))
    assert "deleted" in race_results
    assert set(race_results) <= {"deleted", "resolved", "RECORD_VERSION_CONFLICT"}
    assert service.list_medical_fact_conflicts(context) == []
    with sessions() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        invalidated = db.scalar(
            select(func.count())
            .select_from(MedicalFactConflict)
            .where(
                MedicalFactConflict.patient_id == patient,
                MedicalFactConflict.status == "invalidated",
            )
        )
        members_left = db.scalar(
            select(func.count())
            .select_from(MedicalFactConflictMember)
            .where(MedicalFactConflictMember.conflict_id == UUID(open_after_new_source[0]["id"]))
        )
        race_final_state = db.execute(
            select(
                MedicalFactConflict.status,
                MedicalFactConflict.resolution,
                MedicalFactConflict.resolution_key,
                MedicalFactConflict.request_hash,
                MedicalFactConflict.resolved_at,
                MedicalFactConflict.invalidation_reason_code,
            ).where(MedicalFactConflict.id == stable_conflict_id)
        ).one()
        snapshot_after_delete = AnalysisService._snapshot(db, patient, None, None)
    assert invalidated >= 3 and members_left == 0
    assert race_final_state.status == "invalidated"
    assert race_final_state.resolution is None and race_final_state.resolution_key is None
    assert race_final_state.request_hash is None and race_final_state.resolved_at is None
    assert race_final_state.invalidation_reason_code == "source_deleted"
    assert not any(
        row["record_type"] == "medical_fact_conflict" for row in snapshot_after_delete["records"]
    )
    health_phase = DELETE_PHASES["purge_health"]
    assert health_phase.index("health.medical_fact_conflict_member") < health_phase.index(
        "health.medical_fact_conflict"
    )
    assert health_phase.index("health.medical_fact_conflict") < health_phase.index(
        "health.confirmed_medical_fact"
    )

    app_url, _ = _integration_urls()
    worker_password = os.environ.get(
        "GUTCARE_TEST_PRIVACY_WORKER_PASSWORD", "gutcare-test-privacy-worker-only"
    )
    worker_engine = _engine(
        app_url.set(username="gutcare_privacy_worker", password=worker_password),
        "gutcare-a07-privacy-worker-test",
    )
    storage = S3ObjectStorage(
        os.environ["GUTCARE_TEST_S3_ENDPOINT"],
        os.environ["GUTCARE_TEST_S3_ACCESS_KEY"],
        os.environ["GUTCARE_TEST_S3_SECRET_KEY"],
    )
    pepper, encryption_key = "a07-integration-pepper" * 2, bytes(range(32))
    privacy = PrivacyService(sessions, pepper, storage, encryption_key, integration_bucket)
    operation_id, receipt = privacy.request_deletion(context)
    assert receipt is not None
    worker = PrivacyWorker(
        _sessions(worker_engine), storage, integration_bucket, encryption_key, raise_exceptions=True
    )
    assert worker.process_one() is True
    assert privacy.deletion_status(operation_id, receipt)["status"] == "completed"
    with _sessions(worker_engine)() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM health.medical_fact_conflict WHERE patient_id=:p"),
                {"p": patient},
            )
            == 0
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM health.medical_fact_conflict_member WHERE patient_id=:p"
                ),
                {"p": patient},
            )
            == 0
        )
    worker_engine.dispose()

    # Clean fixture data through the supported account deletion pipeline elsewhere;
    # retaining IDs locally also proves no cross-patient document lookup occurred.
    assert len(source_docs) == 4 and len(same_docs) == 2 and other_patient != patient


def test_f13_receipt_export_wrapped_dek_and_versioned_delete_replay(
    database: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_engine, _migrator_engine = database
    app_url, _ = _integration_urls()
    worker_password = os.environ.get(
        "GUTCARE_TEST_PRIVACY_WORKER_PASSWORD", "gutcare-test-privacy-worker-only"
    )
    worker_url = app_url.set(username="gutcare_privacy_worker", password=worker_password)
    worker_engine = _engine(worker_url, "gutcare-f13-worker-test")
    bucket = os.environ["GUTCARE_TEST_S3_BUCKET"]
    endpoint = os.environ["GUTCARE_TEST_S3_ENDPOINT"]
    access_key = os.environ["GUTCARE_TEST_S3_ACCESS_KEY"]
    secret_key = os.environ["GUTCARE_TEST_S3_SECRET_KEY"]
    raw_s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    try:
        raw_s3.create_bucket(Bucket=bucket)
    except raw_s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    raw_s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    storage = S3ObjectStorage(endpoint, access_key, secret_key)
    key = bytes(range(32))
    sessions = _sessions(app_engine)
    worker_sessions = _sessions(worker_engine)
    privacy = PrivacyService(sessions, "integration-privacy-pepper" * 2, storage, key, bucket)
    user_id, patient_id = _seed_patient(app_engine, nickname="f13-export")
    context = AuthContext(user_id, uuid4())
    other_user, other_patient_id = _seed_patient(app_engine, nickname="f13-other")
    other_context = AuthContext(other_user, uuid4())
    try:
        export_id, categories = privacy.create_export_preview(context, ["profile"])
        assert categories == ["profile"]
        privacy.confirm_export(context, export_id)
        worker = PrivacyWorker(worker_sessions, storage, bucket, key, raise_exceptions=True)
        assert worker.process_export_one() is True
        export_status = privacy.export_status(context, export_id)
        capability = str(export_status["download_capability"])
        archive = privacy.download_export(capability)
        scan_export_zip(archive)
        with pytest.raises(Problem) as replay_download:
            privacy.download_export(capability)
        assert replay_download.value.status == 404
        with pytest.raises(Problem) as cross_patient:
            privacy.export_status(other_context, export_id)
        assert cross_patient.value.status == 404

        # A cancellation concurrent with a successful PUT must remove every
        # version, and the worker must not transition the cancelled row to ready.
        cancel_export_id, _ = privacy.create_export_preview(context, ["profile"])
        privacy.confirm_export(context, cancel_export_id)
        put_finished = Event()
        allow_put_return = Event()

        class PutBarrierStorage:
            def __getattr__(self, name: str) -> Any:
                return getattr(storage, name)

            def put_object(
                self, put_bucket: str, put_key: str, body: bytes, content_type: str
            ) -> None:
                storage.put_object(put_bucket, put_key, body, content_type)
                put_finished.set()
                assert allow_put_return.wait(timeout=10)

        cancel_worker = PrivacyWorker(
            worker_sessions, PutBarrierStorage(), bucket, key, raise_exceptions=True
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            export_future = pool.submit(cancel_worker.process_export_one)
            assert put_finished.wait(timeout=10)
            privacy.cancel_export(context, cancel_export_id)
            allow_put_return.set()
            assert export_future.result(timeout=15) is True
        cancel_object_key = f"exports/{cancel_export_id}.zip.enc"
        assert not [
            version
            for version in storage.list_object_versions(bucket, cancel_object_key)
            if version[0] == cancel_object_key
        ]
        with worker_sessions() as db:
            cancelled = db.get(ExportOperation, cancel_export_id)
            assert cancelled is not None and cancelled.status == "cancelled"
            assert cancelled.object_key == cancel_object_key
        assert worker.cleanup_expired_exports() == 0
        with worker_sessions() as db:
            cancelled = db.get(ExportOperation, cancel_export_id)
            assert cancelled is not None and cancelled.object_key is None

        # Cancellation before PUT must retain the locator until the active worker
        # has either removed the new version or its lease has expired.
        before_put_id, _ = privacy.create_export_preview(context, ["profile"])
        privacy.confirm_export(context, before_put_id)
        before_put_started = Event()
        allow_before_put = Event()

        class BeforePutStorage:
            def __getattr__(self, name: str) -> Any:
                return getattr(storage, name)

            def put_object(
                self, put_bucket: str, put_key: str, body: bytes, content_type: str
            ) -> None:
                before_put_started.set()
                assert allow_before_put.wait(timeout=10)
                storage.put_object(put_bucket, put_key, body, content_type)

        before_worker = PrivacyWorker(
            worker_sessions, BeforePutStorage(), bucket, key, raise_exceptions=True
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            before_future = pool.submit(before_worker.process_export_one)
            assert before_put_started.wait(timeout=10)
            privacy.cancel_export(context, before_put_id)
            before_key = f"exports/{before_put_id}.zip.enc"
            assert worker.cleanup_expired_exports() == 0
            with worker_sessions() as db:
                cancelled = db.get(ExportOperation, before_put_id)
                assert cancelled is not None and cancelled.object_key == before_key
            allow_before_put.set()
            assert before_future.result(timeout=15) is True
        assert not [
            version
            for version in storage.list_object_versions(bucket, before_key)
            if version[0] == before_key
        ]
        assert worker.cleanup_expired_exports() == 0
        with worker_sessions() as db:
            cancelled = db.get(ExportOperation, before_put_id)
            assert cancelled is not None and cancelled.object_key is None

        # A crashed worker can leave a cancelled locator before any PUT occurred.
        # The janitor must clear it without creating a versioned delete marker.
        never_put_id, _ = privacy.create_export_preview(context, ["profile"])
        privacy.confirm_export(context, never_put_id)
        never_key = f"exports/{never_put_id}.zip.enc"
        with worker_sessions.begin() as db:
            row = db.get(ExportOperation, never_put_id)
            assert row is not None
            row.object_key = never_key
            row.lease_owner = "synthetic-crashed-worker"
            row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        privacy.cancel_export(context, never_put_id)
        assert worker.cleanup_expired_exports() == 0
        with worker_sessions() as db:
            row = db.get(ExportOperation, never_put_id)
            assert row is not None and row.object_key is None
        assert not [
            version
            for version in storage.list_object_versions(bucket, never_key)
            if version[0] == never_key
        ]

        # Exercise export budgets using a small test limit while keeping the
        # storage HEAD authoritative (the database metadata is deliberately 1).
        import gutcare.privacy.worker as privacy_worker_module

        monkeypatch.setattr(privacy_worker_module, "MAX_EXPORT_BYTES", 256)
        oversized_key = f"export-bound/{uuid4()}.bin"
        storage.put_object(bucket, oversized_key, b"x" * 257, "application/octet-stream")
        with sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"),
                {"id": str(patient_id)},
            )
            db.add(
                FileObject(
                    patient_id=patient_id,
                    bucket_name=bucket,
                    object_key=oversized_key,
                    original_name="oversized.bin",
                    content_type="application/octet-stream",
                    size_bytes=1,
                    content_sha256="c" * 64,
                    sensitivity="normal",
                    scan_status="clean",
                    storage_status="available",
                )
            )
        with sessions() as db:
            datasets, attachments = worker._export_payload(db, patient_id, ["files"])
        assert attachments == []
        assert datasets["unavailable_file_ids"]
        file_metadata = datasets["files"]
        assert isinstance(file_metadata, list) and file_metadata[0]["size_bytes"] == 1

        json_export_id, _ = privacy.create_export_preview(context, ["profile"])
        privacy.confirm_export(context, json_export_id)
        json_worker = PrivacyWorker(worker_sessions, storage, bucket, key)
        json_worker._export_payload = lambda _db, _patient, _categories: (
            {"oversized": "x" * 300},
            [],
        )
        assert json_worker.process_export_one() is True
        with worker_sessions() as db:
            oversized_json = db.get(ExportOperation, json_export_id)
            assert oversized_json is not None and oversized_json.status == "pending"
            assert oversized_json.last_error_code == "EXPORT_BUILD_FAILED"

        with worker_sessions() as db:
            exported = db.get(ExportOperation, export_id)
            assert exported is not None and exported.wrapped_dek is not None
            assert len(exported.wrapped_dek) == 60
            assert exported.wrapped_dek[12:] != key
            object_key = exported.object_key
            assert object_key is not None
        # Two versions of one export artefact exercise MinIO version inventory/deletion.
        storage.put_object(bucket, object_key, b"new-export-version", "application/octet-stream")
        versions_before = [
            row for row in storage.list_object_versions(bucket, object_key) if row[0] == object_key
        ]
        assert len(versions_before) >= 2

        # Concurrent idempotent requests converge on one deletion operation; only its
        # creator receives the single-use receipt, and retries never rotate it.
        barrier = Barrier(2)

        def request_delete() -> tuple[UUID, str | None]:
            barrier.wait(timeout=5)
            return privacy.request_deletion(context)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: request_delete(), range(2)))
        operation_ids = {row[0] for row in results}
        assert len(operation_ids) == 1
        operation_id = results[0][0]
        receipts = [receipt for _, receipt in results if receipt is not None]
        assert len(receipts) == 1
        accepted_receipt = receipts[0]
        assert accepted_receipt is not None
        with pytest.raises(Problem) as invalid_receipt:
            privacy.deletion_status(operation_id, "incorrect-receipt")
        assert invalid_receipt.value.status == 404
        assert privacy.deletion_status(operation_id, accepted_receipt)["status"] in {
            "pending",
            "processing",
        }
        with sessions() as db:
            account = db.get(UserAccount, user_id)
            assert account is not None and account.status == "deactivated"
            assert not db.scalar(
                text(
                    "SELECT has_column_privilege('gutcare_app','privacy.deletion_operation','patient_id','UPDATE')"
                )
            )
            assert db.scalar(
                text(
                    "SELECT has_column_privilege('gutcare_app','privacy.deletion_operation','receipt_hash','UPDATE')"
                )
            )

        # Force the SLA branch, then replay a simulated expired lease and finish all phases.
        with worker_sessions.begin() as db:
            operation = db.get(DeletionOperation, operation_id)
            assert operation is not None
            operation.due_at = datetime.now(UTC) - timedelta(days=1)
        worker = PrivacyWorker(worker_sessions, storage, bucket, key, raise_exceptions=True)
        claim_barrier = Barrier(2)

        def claim_deletion() -> UUID | None:
            claim_barrier.wait(timeout=5)
            return worker.claim()

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: claim_deletion(), range(2)))
        assert claims.count(operation_id) == 1
        assert claims.count(None) == 1
        with worker_sessions.begin() as db:
            claimed = db.get(DeletionOperation, operation_id)
            assert claimed is not None and claimed.status == "overdue"
            claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        class CrashAfterObjectPhase(PrivacyWorker):
            def _step_exists(self, op_id: UUID, code: str) -> bool:
                if code == "purge_derived":
                    raise RuntimeError("synthetic crash after object phase")
                return super()._step_exists(op_id, code)

        crashing_worker = CrashAfterObjectPhase(
            worker_sessions, storage, bucket, key, raise_exceptions=True
        )
        with pytest.raises(RuntimeError, match="synthetic crash after object phase"):
            crashing_worker.process_one()
        with worker_sessions.begin() as db:
            operation = db.get(DeletionOperation, operation_id)
            assert operation is not None
            assert db.get(DeletionStep, (operation_id, "delete_objects")) is not None
            operation.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        # Simulate a delayed object write after the durable delete_objects checkpoint.
        late_key = f"late-version/{uuid4()}.bin"
        storage.put_object(bucket, late_key, b"late-v1", "application/octet-stream")
        storage.put_object(bucket, late_key, b"late-v2", "application/octet-stream")
        with sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"),
                {"id": str(patient_id)},
            )
            db.add(
                FileObject(
                    patient_id=patient_id,
                    bucket_name=bucket,
                    object_key=late_key,
                    original_name="late.bin",
                    content_type="application/octet-stream",
                    size_bytes=8,
                    content_sha256="b" * 64,
                    sensitivity="normal",
                    scan_status="clean",
                    storage_status="available",
                )
            )
        assert worker.process_one() is True
        assert not [
            row for row in storage.list_object_versions(bucket, late_key) if row[0] == late_key
        ]
        with worker_sessions() as db:
            operation = db.get(DeletionOperation, operation_id)
            assert operation is not None
            assert operation.status == "completed"
            assert operation.patient_id is None
            steps = set(
                db.scalars(
                    select(DeletionStep.step_code).where(
                        DeletionStep.operation_id == operation_id,
                        DeletionStep.status == "completed",
                    )
                ).all()
            )
            assert {
                "freeze",
                "inventory",
                "revoke_capabilities",
                "delete_objects",
                "purge_derived",
                "purge_health",
                "purge_identity",
                "finalize",
            } <= steps
            late_inventory = db.scalars(
                select(ObjectInventory).where(
                    ObjectInventory.operation_id == operation_id,
                    ObjectInventory.source_code == "file_object",
                )
            ).all()
            assert any(row.object_key is None and row.status == "deleted" for row in late_inventory)

        # A storage failure is retried with exponential delay; an eighth attempt
        # becomes dead-letter and must block --replay/readiness.
        failed_key = f"privacy-replay-failure/{uuid4()}.bin"
        with sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"),
                {"id": str(other_patient_id)},
            )
            db.add(
                FileObject(
                    patient_id=other_patient_id,
                    bucket_name=bucket,
                    object_key=failed_key,
                    original_name="failure.bin",
                    content_type="application/octet-stream",
                    size_bytes=8,
                    content_sha256="a" * 64,
                    sensitivity="normal",
                    scan_status="clean",
                    storage_status="available",
                )
            )
        failure_operation_id, _ = privacy.request_deletion(other_context)

        class FailingStorage:
            def list_object_versions(
                self, _bucket: str, prefix: str
            ) -> list[tuple[str, str | None]]:
                return [(prefix, "v1")]

            def delete_object_version(
                self, _bucket: str, _object_key: str, _version_id: str | None
            ) -> None:
                raise RuntimeError("synthetic object deletion failure")

        failing_worker = PrivacyWorker(
            worker_sessions,
            FailingStorage(),
            bucket,
            key,  # type: ignore[arg-type]
        )
        assert failing_worker.process_one() is True
        with worker_sessions.begin() as db:
            failed_operation = db.get(DeletionOperation, failure_operation_id)
            assert failed_operation is not None and failed_operation.attempts == 1
            assert failed_operation.status == "pending"
            retry_at = failed_operation.lease_expires_at
            assert retry_at is not None and retry_at > datetime.now(UTC)
            failed_operation.attempts = 7
            failed_operation.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert failing_worker.process_one() is True
        with worker_sessions() as db:
            failed_operation = db.get(DeletionOperation, failure_operation_id)
            assert failed_operation is not None and failed_operation.status == "dead_letter"
            assert (
                db.scalar(
                    text(
                        "SELECT count(*) FROM privacy.deletion_operation WHERE status IN ('pending','overdue','processing','dead_letter')"
                    )
                )
                >= 1
            )
            assert (
                db.scalar(
                    select(func.count(ObjectInventory.id)).where(
                        ObjectInventory.operation_id == failure_operation_id
                    )
                )
                == 1
            )
            inventory = db.scalars(
                select(ObjectInventory).where(ObjectInventory.operation_id == operation_id)
            ).all()
            assert len(inventory) >= 2
            assert all(row.object_key is None and row.status == "deleted" for row in inventory)
            assert all(row.key_digest_ciphertext for row in inventory)
            audit = db.scalar(
                text("SELECT expires_at FROM privacy.security_audit WHERE operation_hash=:hash"),
                {"hash": operation.account_hash},
            )
            assert audit is not None and audit > datetime.now(UTC) + timedelta(days=179)
        # Remove only this synthetic dead-letter fixture so it cannot intentionally
        # block the later backup/restore readiness gate.
        with worker_sessions.begin() as db:
            db.execute(
                text("DELETE FROM privacy.deletion_operation WHERE id=:id"),
                {"id": failure_operation_id},
            )
        with worker_sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"),
                {"id": str(other_patient_id)},
            )
            db.execute(
                text(
                    "DELETE FROM health.file_object WHERE patient_id=:patient AND object_key=:key"
                ),
                {"patient": other_patient_id, "key": failed_key},
            )
        assert not [
            row for row in storage.list_object_versions(bucket, object_key) if row[0] == object_key
        ]
        with app_engine.connect() as db:
            assert (
                db.scalar(
                    text("SELECT count(*) FROM health.patient_profile WHERE id=:id"),
                    {"id": patient_id},
                )
                == 0
            )
            assert (
                db.scalar(
                    text("SELECT count(*) FROM iam.user_account WHERE id=:id"), {"id": user_id}
                )
                == 0
            )
    finally:
        worker_engine.dispose()


def test_f07_f11_postgres18_activity_history_and_aggregates(database: Any) -> None:
    """T87-T90: real PG18 RLS, CRUD/version/delete, mixed cursor and SQL metrics."""
    app_engine, migrator_engine = database
    user_a, patient_a = _seed_patient(app_engine, nickname="stage9-a")
    user_b, patient_b = _seed_patient(app_engine, nickname="stage9-b")
    context_a = AuthContext(user_id=user_a, session_id=uuid4())
    context_b = AuthContext(user_id=user_b, session_id=uuid4())
    service = ActivityService(
        _sessions(app_engine), "integration-only-signing-key-000000000000000000000000"
    )
    occurred = datetime(2026, 3, 8, 8, 30, tzinfo=UTC)
    body = {
        "activity_type": "walking",
        "description": None,
        "intensity": "moderate",
        "subjective_feeling": "same",
        "duration_minutes": 30,
        "occurred_at": occurred,
    }
    first = service.create(context_a, body)
    second = service.create(
        context_a, {**body, "occurred_at": datetime(2026, 3, 8, 8, 30, 1, tzinfo=UTC)}
    )
    assert second["id"] != first["id"]
    assert service.get(context_a, UUID(first["id"]))["record_version"] == 1
    with pytest.raises(Problem) as cross_patient:
        service.get(context_b, UUID(first["id"]))
    assert cross_patient.value.status == 404
    with pytest.raises(Problem) as stale:
        service.update(context_a, UUID(first["id"]), 2, {"duration_minutes": 60})
    assert stale.value.code == "RECORD_VERSION_CONFLICT"
    updated = service.update(context_a, UUID(first["id"]), 1, {"duration_minutes": 45})
    assert updated["record_version"] == 2
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)})
        diet = DietRecord(
            patient_id=patient_a,
            occurred_at=occurred,
            payload={},
            source_type="patient_manual",
            confirmation_status="confirmed",
            record_version=1,
        )
        symptom = SymptomRecord(
            patient_id=patient_a,
            occurred_at=occurred,
            symptom_status="ongoing",
            payload={},
            source_type="patient_manual",
            record_version=1,
        )
        db.add_all([diet, symptom])
        db.flush()
        db.add_all(
            [
                DietItem(
                    diet_record_id=diet.id,
                    patient_id=patient_a,
                    name="合成乳制品",
                    category_code="dairy",
                    confirmed_by_patient=True,
                ),
                DietItem(
                    diet_record_id=diet.id,
                    patient_id=patient_a,
                    name="未确认候选",
                    category_code="other",
                    confirmed_by_patient=False,
                ),
                SymptomItem(
                    symptom_record_id=symptom.id,
                    patient_id=patient_a,
                    symptom_code="bloating",
                    severity=5,
                    patient_confirmed=True,
                ),
            ]
        )
        db.add(
            StoolRecord(
                patient_id=patient_a,
                occurred_at=occurred,
                bristol_type=3,
                payload={},
                source_type="patient_manual",
                confirmation_status="confirmed",
                record_version=1,
            )
        )
        advice_task = AnalysisTask(patient_id=patient_a, analysis_type="periodic_summary")
        db.add(advice_task)
        db.flush()
        db.add(
            TaskInputSnapshot(
                task_id=advice_task.id,
                patient_id=patient_a,
                snapshot_payload={"source": "integration-test"},
                content_hash="a" * 64,
            )
        )
        db.add(
            HealthAdvice(
                patient_id=patient_a,
                task_id=advice_task.id,
                category="diet",
                priority="routine",
                title="Synthetic advice",
                body="Synthetic body",
                uncertainty={},
                applicability={},
                safety_boundary={},
                version="test-v1",
            )
        )
        second_task = AnalysisTask(patient_id=patient_a, analysis_type="periodic_summary")
        db.add(second_task)
        db.flush()
        db.add(
            TaskInputSnapshot(
                task_id=second_task.id,
                patient_id=patient_a,
                snapshot_payload={"source": "integration-test-delete"},
                content_hash="b" * 64,
            )
        )
        db.add(
            HealthAdvice(
                patient_id=patient_a,
                task_id=second_task.id,
                category="diet",
                priority="routine",
                title="Synthetic advice to delete",
                body="Synthetic body",
                uncertainty={},
                applicability={},
                safety_boundary={},
                version="test-v1",
            )
        )
        db.add(
            StoolRecord(
                patient_id=patient_a,
                occurred_at=datetime(2026, 3, 8, 9, 0, tzinfo=UTC),
                bristol_type=None,
                payload={},
                source_type="patient_manual",
                confirmation_status="confirmed",
                record_version=1,
            )
        )
        for state in ("pending", "taken", "not_taken", "skipped"):
            plan = MedicationPlan(
                patient_id=patient_a,
                medication_name="Synthetic",
                source_type="manual",
                confirmation_status="confirmed",
                plan_status="active",
                record_version=1,
            )
            db.add(plan)
            db.flush()
            schedule = MedicationSchedule(
                plan_id=plan.id,
                patient_id=patient_a,
                local_time=local_time(8, 0),
                timezone="Asia/Shanghai",
                valid_from=date(2026, 3, 8),
                enabled=True,
                record_version=1,
            )
            db.add(schedule)
            db.flush()
            db.add(
                MedicationCheckin(
                    schedule_id=schedule.id,
                    patient_id=patient_a,
                    local_date=date(2026, 3, 8),
                    scheduled_for=occurred,
                    status=state,
                    record_version=1,
                    taken_at=occurred if state == "taken" else None,
                )
            )
        db.execute(
            text("UPDATE health.medication_plan SET plan_status='ended' WHERE patient_id=:p"),
            {"p": patient_a},
        )
    timeline1 = service.timeline(context_a, 1, None, None, None, None)
    timeline2 = service.timeline(context_a, 1, timeline1["next_cursor"], None, None, None)
    assert timeline1["items"] and timeline2["items"]
    assert timeline1["items"][0]["id"] != timeline2["items"][0]["id"]
    assert service._decode(timeline1["next_cursor"])["type"] == "advice"
    advice_page = service.timeline(context_a, 10, None, ["advice"], None, None)
    assert len(advice_page["items"]) == 2
    assert all(item["target"]["type"] == "advice" for item in advice_page["items"])
    advice_ids = [UUID(item["target"]["id"]) for item in advice_page["items"]]
    advice_id = advice_ids[0]
    delete_advice_id = advice_ids[1]
    all_ids: set[str] = set()
    page_cursor = None
    for _ in range(20):
        page = service.timeline(context_a, 1, page_cursor, None, None, None)
        all_ids.update(item["target"]["id"] for item in page["items"])
        page_cursor = page["next_cursor"]
        if page_cursor is None:
            break
    assert str(advice_id) in all_ids
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)})
        assert db.scalar(select(HealthAdvice.id).where(HealthAdvice.id == advice_id)) == advice_id
        delete_task_id = db.scalar(
            select(HealthAdvice.task_id).where(HealthAdvice.id == delete_advice_id)
        )
        db.execute(
            text("UPDATE analysis.health_advice SET archived_at=now() WHERE id=:id"),
            {"id": advice_id},
        )
    with migrator_engine.begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)})
        db.execute(text("DELETE FROM analysis.analysis_task WHERE id=:id"), {"id": delete_task_id})
    assert service.timeline(context_a, 10, None, ["advice"], None, None)["items"] == []
    trend = service.trends(
        context_a,
        datetime(2026, 3, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 3, 9, 0, 0, tzinfo=UTC),
        "day",
    )
    assert trend["activity"]["has_data"] is True
    assert trend["activity"]["items"][0]["duration_minutes"] == 75
    assert trend["stool"]["items"][0]["bristol_confirmed_count"] == 1
    assert trend["stool"]["items"][0]["bristol_unknown_count"] == 1
    assert trend["symptom"]["items"][0]["mean_severity"] == 5.0
    assert trend["symptom"]["items"][0]["status"] == "ongoing"
    assert trend["diet_confirmed_categories"]["items"] == [
        {"bucket": "2026-03-08T00:00:00", "category": "dairy", "count": 1}
    ]
    assert {row["status"] for row in trend["medication_checkins"]["items"]} == {
        "pending",
        "taken",
        "not_taken",
        "skipped",
    }
    assert sum(row["count"] for row in trend["medication_checkins"]["items"]) == 4
    assert service.trends(
        context_b,
        datetime(2026, 3, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 3, 9, 0, 0, tzinfo=UTC),
        "day",
    )["activity"] == {"has_data": False, "items": []}
    service.delete(context_a, UUID(first["id"]), 2)
    with pytest.raises(Problem) as deleted:
        service.get(context_a, UUID(first["id"]))
    assert deleted.value.status == 404
    page = service.list_activities(context_a, 100, None, occurred, occurred + timedelta(seconds=1))
    assert all(item["id"] != first["id"] for item in page["items"])
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)})
        assert (
            db.scalar(
                select(func.count())
                .select_from(ActivityRecord)
                .where(ActivityRecord.deleted_at.is_(None))
            )
            == 1
        )
        db.execute(
            text(
                "INSERT INTO health.activity_record(patient_id,activity_type,intensity,subjective_feeling,duration_minutes,occurred_at) "
                "SELECT :p,'walking','low','same',30,TIMESTAMPTZ '2025-01-01 00:00:00+00' + g * interval '1 minute' "
                "FROM generate_series(1, 5000) AS g"
            ),
            {"p": patient_a},
        )
        db.execute(text("ANALYZE health.activity_record"))
        plan_text = "\n".join(
            db.scalars(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT id FROM health.activity_record WHERE patient_id=:p AND occurred_at >= :lo AND occurred_at < :hi ORDER BY occurred_at"
                ),
                {
                    "p": patient_a,
                    "lo": datetime(2025, 1, 1, tzinfo=UTC),
                    "hi": datetime(2025, 1, 1, 0, 2, tzinfo=UTC),
                },
            ).all()
        )
        assert "ix_activity_record_patient_occurred" in plan_text and "Buffers:" in plan_text

    # The two repeated wall-clock 01:30 times at the New York fall-back transition share one local day bucket.
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_a)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient_a)})
        db.execute(
            text("UPDATE health.patient_profile SET timezone='America/New_York' WHERE id=:p"),
            {"p": patient_a},
        )
    service.create(context_a, {**body, "occurred_at": datetime(2026, 11, 1, 5, 30, tzinfo=UTC)})
    service.create(context_a, {**body, "occurred_at": datetime(2026, 11, 1, 6, 30, tzinfo=UTC)})
    dst = service.trends(
        context_a,
        datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 5, 0, tzinfo=UTC),
        "day",
    )
    assert dst["timezone"] == "America/New_York"
    assert dst["activity"]["items"] == [
        {
            "bucket": "2026-11-01T00:00:00",
            "count": 2,
            "duration_minutes": 60,
        }
    ]
    empty = service.trends(
        context_b,
        datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 5, 0, tzinfo=UTC),
        "day",
    )
    assert empty["activity"] == {"has_data": False, "items": []}


def _f09_postgres18_callback_feedback_projection_and_isolation(database: Any) -> None:
    """T72/T74-T79: advice stays separate, snapshot-bound and patient isolated."""
    app_engine, migrator_engine = database
    worker_raw = os.environ.get("GUTCARE_TEST_ANALYSIS_WORKER_DATABASE_URL")
    if not worker_raw:
        pytest.skip("Set GUTCARE_TEST_ANALYSIS_WORKER_DATABASE_URL for F09 gates.")
    worker_engine = _engine(make_url(worker_raw), "gutcare-pg18-advice-worker")
    try:
        user_a, patient_a = _seed_patient(app_engine, nickname="f09-a")
        user_b, patient_b = _seed_patient(app_engine, nickname="f09-b")
        context_a = AuthContext(user_id=user_a, session_id=uuid4())
        context_b = AuthContext(user_id=user_b, session_id=uuid4())
        with _sessions(app_engine).begin() as db:
            for patient_id in (patient_a, patient_b):
                db.execute(
                    text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_id)}
                )
                for kind in ("health_data_processing", "third_party_ai"):
                    db.add(
                        PatientConsent(
                            patient_id=patient_id,
                            consent_type=kind,
                            document_version="t-v1",
                            granted=True,
                            decided_at=utc_now(),
                            metadata_json={"notice_summary_hash": "a" * 64},
                        )
                    )
                db.add(
                    DietRecord(
                        patient_id=patient_id,
                        occurred_at=utc_now(),
                        meal_type="lunch",
                        confirmation_status="confirmed",
                        record_version=3,
                    )
                )
                if patient_id == patient_a:
                    parse_request = MedicalParseRequest(
                        patient_id=patient_a,
                        document_id=None,
                        file_object_id=None,
                        record_version=1,
                        status="succeeded",
                    )
                    db.add(parse_request)
                    db.flush()
                    diagnosis_candidate = MedicalFieldCandidate(
                        patient_id=patient_a,
                        request_id=parse_request.id,
                        field_code="diagnosis",
                        value_type="diagnosis",
                        value={"text": "IBS", "certainty": "suspected"},
                        unit=None,
                        confidence=0.8,
                        uncertainty="integration candidate",
                        source_locator={"page": 1},
                        excerpt="consider IBS",
                        review_status="accepted",
                    )
                    db.add(diagnosis_candidate)
                    db.flush()
                    db.add(
                        ConfirmedMedicalFact(
                            patient_id=patient_a,
                            candidate_id=diagnosis_candidate.id,
                            field_code="diagnosis",
                            value_type="diagnosis",
                            value={"text": "IBS", "certainty": "suspected"},
                            unit=None,
                            fact_status="active",
                        )
                    )

        task_service = AnalysisService(_sessions(app_engine))
        created, _ = task_service.create(
            context_a,
            {
                "analysis_type": "comprehensive_health_analysis",
                "requested_from": None,
                "requested_to": None,
            },
            "f09-analysis-task-0001",
        )
        task_id = UUID(created["id"])
        worker = AnalysisService(_sessions(worker_engine))
        assert worker.claim()["task_id"] == str(task_id)
        inputs = worker.inputs(task_id)
        source = next(row for row in inputs["records"] if row["record_type"] == "diet_record")
        assert any(
            row["record_type"] == "confirmed_medical_fact"
            and row["payload"]["value"].get("certainty") == "suspected"
            for row in inputs["records"]
        )
        worker.result(
            task_id,
            uuid4(),
            {
                "callback_id": str(uuid4()),
                "status": "succeeded",
                "schema_version": "1.0",
                "summary": "summary",
                "observations": [],
                "evidence": [
                    {
                        "source_type": source["record_type"],
                        "source_id": source["record_id"],
                        "source_version": source["record_version"],
                        "locator": source["locator"],
                    }
                ],
                "uncertainties": [],
                "missing_data": [],
            },
        )

        advice_service = AdviceService(_sessions(worker_engine))
        patient_advice_service = AdviceService(_sessions(app_engine))
        callback_id = uuid4()
        advice_payload = {
            "callback_id": str(callback_id),
            "schema_version": "1.0",
            "advice": [
                {
                    "category": "diet",
                    "priority": "routine",
                    "title": "Keep a meal record",
                    "body": "Continue recording meals for review.",
                    "uncertainty": {"level": "moderate", "reasons": ["Limited observations"]},
                    "applicability": {"scope": "general", "limitations": []},
                    "safety_boundary": {
                        "not_diagnosis": True,
                        "not_prescription": True,
                        "risk_alert_priority": True,
                    },
                    "version": "1.0",
                    "evidence": [
                        {
                            "evidence_type": "patient",
                            "source_type": source["record_type"],
                            "source_id": source["record_id"],
                            "source_version": source["record_version"],
                            "locator": source["locator"],
                        }
                    ],
                }
            ],
        }
        condition_specific_payload = {
            **advice_payload,
            "callback_id": str(uuid4()),
            "advice": [
                {
                    **advice_payload["advice"][0],
                    "applicability": {"scope": "condition_specific", "limitations": []},
                }
            ],
        }
        with pytest.raises(Problem) as inapplicable:
            advice_service.callback(task_id, condition_specific_payload)
        assert inapplicable.value.code == "ADVICE_NOT_APPLICABLE"
        with _sessions(migrator_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdviceCallback)
                    .where(
                        AdviceCallback.task_id == task_id,
                        AdviceCallback.callback_id
                        == UUID(condition_specific_payload["callback_id"]),
                    )
                )
                == 0
            )
        advice_service.callback(task_id, advice_payload)
        advice_service.callback(task_id, advice_payload)
        assert len(patient_advice_service.list(context_a, 20)["items"]) == 1
        advice_id = UUID(patient_advice_service.list(context_a, 20)["items"][0]["id"])
        with pytest.raises(Problem) as wrong_digest:
            advice_service.callback(
                task_id,
                {**advice_payload, "advice": [{**advice_payload["advice"][0], "title": "changed"}]},
            )
        assert wrong_digest.value.status == 409
        with pytest.raises(Problem) as cross_patient:
            patient_advice_service.get(context_b, advice_id)
        assert cross_patient.value.status == 404

        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            source_row = db.scalar(select(DietRecord).where(DietRecord.patient_id == patient_a))
            assert source_row is not None
            source_row.record_version = 4
        projected = patient_advice_service.get(context_a, advice_id)
        assert projected["basis_updated"] is True
        assert projected["basis_update_reason"] == "source_updated"
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            persisted = db.get(HealthAdvice, advice_id)
            assert persisted is not None and persisted.basis_updated is True
            assert persisted.basis_update_reason == "source_updated"
        assert patient_advice_service.mark_read(context_a, advice_id)["basis_updated"] is True
        feedback = patient_advice_service.feedback(
            context_a,
            advice_id,
            {"feedback_type": "helpful", "expected_version": 0},
            "f09-feedback-key-0001",
        )
        assert feedback["version"] == 1
        assert (
            patient_advice_service.feedback(
                context_a,
                advice_id,
                {"feedback_type": "helpful", "expected_version": 0},
                "f09-feedback-key-0001",
            )["version"]
            == 1
        )
        changed_feedback = patient_advice_service.feedback(
            context_a,
            advice_id,
            {"feedback_type": "not_applicable", "expected_version": 1},
            "f09-feedback-key-0002",
        )
        assert changed_feedback["version"] == 2
        with pytest.raises(Problem):
            patient_advice_service.feedback(
                context_a,
                advice_id,
                {"feedback_type": "not_helpful", "expected_version": 1},
                "f09-feedback-key-0003",
            )

        # Two writers with distinct keys and the same optimistic version: exactly one wins.
        second_callback = {**advice_payload, "callback_id": str(uuid4())}
        advice_service.callback(task_id, second_callback)
        page_one = patient_advice_service.list(context_a, 1)
        assert len(page_one["items"]) == 1 and page_one["next_cursor"]
        page_two = patient_advice_service.list(context_a, 1, page_one["next_cursor"])
        assert len(page_two["items"]) == 1 and page_two["next_cursor"] is None
        assert {item["id"] for item in page_one["items"] + page_two["items"]} == {
            item["id"] for item in patient_advice_service.list(context_a, 20)["items"]
        }
        concurrent_advice_id = UUID(page_one["items"][0]["id"])
        distinct_barrier = Barrier(2)

        def distinct_feedback(key: str, feedback_type: str) -> dict[str, Any] | int:
            distinct_barrier.wait(timeout=5)
            try:
                return patient_advice_service.feedback(
                    context_a,
                    concurrent_advice_id,
                    {"feedback_type": feedback_type, "expected_version": 0},
                    key,
                )
            except Problem as exc:
                return exc.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            competing = [
                executor.submit(distinct_feedback, "f09-race-a-0001", "helpful"),
                executor.submit(distinct_feedback, "f09-race-b-0001", "not_helpful"),
            ]
            distinct_results = [future.result(timeout=10) for future in competing]
        assert (
            sum(isinstance(result, dict) and result["version"] == 1 for result in distinct_results)
            == 1
        )
        assert sum(result == 409 for result in distinct_results) == 1
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            current = db.get(AdviceFeedback, (concurrent_advice_id, patient_a))
            assert current is not None and current.version == 1
            committed_feedback_type = current.feedback_type
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdviceFeedbackEvent)
                    .where(AdviceFeedbackEvent.advice_id == concurrent_advice_id)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdviceFeedbackEvent)
                    .where(
                        AdviceFeedbackEvent.idempotency_key.in_(
                            ["f09-race-a-0001", "f09-race-b-0001"]
                        )
                    )
                )
                == 1
            )

        # Same key + same body concurrently replays one response/event.
        replay_barrier = Barrier(2)

        def replay_feedback() -> dict[str, Any]:
            replay_barrier.wait(timeout=5)
            return patient_advice_service.feedback(
                context_a,
                concurrent_advice_id,
                {"feedback_type": committed_feedback_type, "expected_version": 1},
                "f09-race-replay-0001",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            replay_results = list(executor.map(lambda _: replay_feedback(), range(2)))
        assert replay_results[0] == replay_results[1]
        assert replay_results[0]["version"] == 2
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            replay_current = db.get(AdviceFeedback, (concurrent_advice_id, patient_a))
            assert replay_current is not None and replay_current.version == 2
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdviceFeedbackEvent)
                    .where(AdviceFeedbackEvent.advice_id == concurrent_advice_id)
                )
                == 2
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdviceFeedbackEvent)
                    .where(AdviceFeedbackEvent.idempotency_key == "f09-race-replay-0001")
                )
                == 1
            )

        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            source_row = db.scalar(select(DietRecord).where(DietRecord.patient_id == patient_a))
            assert source_row is not None
            source_row.deleted_at = utc_now()
        deleted_projection = patient_advice_service.archive(context_a, advice_id)
        assert deleted_projection["basis_updated"] is True
        patient_evidence = next(
            item for item in deleted_projection["evidence"] if item["evidence_type"] == "patient"
        )
        assert patient_evidence["source_deleted"] is True
        assert patient_evidence["locator"] is None and patient_evidence["target"] is None
        assert deleted_projection["body"] == "Continue recording meals for review."
        assert deleted_projection["status"] == "archived"
        assert len(deleted_projection["feedback_history"]) == 2
        assert not any("body" in item for item in deleted_projection["evidence"])

        with migrator_engine.connect() as db:
            assert (
                db.scalar(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE oid='analysis.health_advice'::regclass"
                    )
                )
                is True
            )
            assert (
                db.scalar(
                    text(
                        "SELECT has_table_privilege('gutcare_analysis_worker', "
                        "'analysis.advice_feedback', 'INSERT')"
                    )
                )
                is False
            )
        with _sessions(worker_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
            )
            assert (
                db.scalar(select(HealthAdvice.id).where(HealthAdvice.id == advice_id)) == advice_id
            )
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_b)}
            )
            assert db.scalar(select(HealthAdvice.id).where(HealthAdvice.id == advice_id)) is None

        # Account freeze and advice callback share the patient consent fence.
        user_c, patient_c = _seed_patient(app_engine, nickname="f09-freeze")
        context_c = AuthContext(user_id=user_c, session_id=uuid4())
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_c)}
            )
            for kind in ("health_data_processing", "third_party_ai"):
                db.add(
                    PatientConsent(
                        patient_id=patient_c,
                        consent_type=kind,
                        document_version="t-v1",
                        granted=True,
                        decided_at=utc_now(),
                        metadata_json={"notice_summary_hash": "b" * 64},
                    )
                )
            db.add(
                DietRecord(
                    patient_id=patient_c,
                    occurred_at=utc_now(),
                    meal_type="breakfast",
                    confirmation_status="confirmed",
                    record_version=1,
                )
            )
        freeze_task, _ = task_service.create(
            context_c,
            {
                "analysis_type": "comprehensive_health_analysis",
                "requested_from": None,
                "requested_to": None,
            },
            "f09-freeze-analysis-task-01",
        )
        freeze_task_id = UUID(freeze_task["id"])
        assert worker.claim()["task_id"] == str(freeze_task_id)
        freeze_inputs = worker.inputs(freeze_task_id)
        freeze_source = freeze_inputs["records"][0]
        worker.result(
            freeze_task_id,
            uuid4(),
            {
                "callback_id": str(uuid4()),
                "status": "succeeded",
                "schema_version": "1.0",
                "summary": "summary",
                "observations": [],
                "evidence": [],
                "uncertainties": [],
                "missing_data": [],
            },
        )
        freeze_payload = {
            **advice_payload,
            "callback_id": str(uuid4()),
            "advice": [
                {
                    **advice_payload["advice"][0],
                    "evidence": [
                        {
                            "evidence_type": "patient",
                            "source_type": freeze_source["record_type"],
                            "source_id": freeze_source["record_id"],
                            "source_version": freeze_source["record_version"],
                            "locator": freeze_source["locator"],
                        }
                    ],
                }
            ],
        }
        race_barrier = Barrier(2)

        def submit_while_freezing() -> str:
            race_barrier.wait(timeout=5)
            try:
                advice_service.callback(freeze_task_id, freeze_payload)
                return "callback"
            except Problem as exc:
                return exc.code

        def freeze_account() -> UUID:
            race_barrier.wait(timeout=5)
            return _service(app_engine).request_account_deletion(context_c)

        with ThreadPoolExecutor(max_workers=2) as executor:
            callback_future = executor.submit(submit_while_freezing)
            deletion_future = executor.submit(freeze_account)
            callback_outcome = callback_future.result(timeout=10)
            assert deletion_future.result(timeout=10)
        assert callback_outcome in {"callback", "CONSENT_REQUIRED"}
        with _sessions(worker_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_c)}
            )
            freeze_advice_count = db.scalar(
                select(HealthAdvice.id).where(HealthAdvice.task_id == freeze_task_id)
            )
            assert (freeze_advice_count is not None) is (callback_outcome == "callback")
    finally:
        worker_engine.dispose()


def test_f06_postgres18_rls_idempotency_and_materializer(database: Any) -> None:
    """T56-T59: PG18 ownership, immutable replay, schedule history, worker concurrency."""
    app_engine, migrator_engine = database
    user_a, patient_a = _seed_patient(app_engine, nickname="f06-a")
    user_b, _patient_b = _seed_patient(app_engine, nickname="f06-b")
    service = MedicationService(_sessions(app_engine))
    context_a = AuthContext(user_id=user_a, session_id=uuid4())
    context_b = AuthContext(user_id=user_b, session_id=uuid4())
    start_date = date.today() + timedelta(days=1)
    plan = service.create_plan(
        context_a,
        {
            "medication_name": "synthetic-plan",
            "source_type": "manual",
            "source_document_id": None,
            "dosage_text": None,
            "route_code": None,
            "start_date": start_date,
            "end_date": start_date + timedelta(days=10),
        },
        "f06-idempotency-0001",
    )
    replay = service.create_plan(
        context_a,
        {
            "medication_name": "synthetic-plan",
            "source_type": "manual",
            "source_document_id": None,
            "dosage_text": None,
            "route_code": None,
            "start_date": start_date,
            "end_date": start_date + timedelta(days=10),
        },
        "f06-idempotency-0001",
    )
    assert replay["id"] == plan["id"]
    with pytest.raises(Problem) as conflict:
        service.create_plan(
            context_a,
            {"medication_name": "different", "source_type": "manual", "source_document_id": None},
            "f06-idempotency-0001",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    confirmed = service.transition_plan(
        context_a, UUID(plan["id"]), 1, "confirm", "f06-confirm-0001"
    )
    service.transition_plan(context_a, UUID(plan["id"]), 2, "activate", "f06-activate-001")
    assert (
        service.transition_plan(context_a, UUID(plan["id"]), 1, "confirm", "f06-confirm-0001")
        == confirmed
    )
    with pytest.raises(Problem) as transition_conflict:
        service.transition_plan(context_a, UUID(plan["id"]), 1, "review", "f06-confirm-0001")
    assert transition_conflict.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(Problem) as active_review:
        service.transition_plan(context_a, UUID(plan["id"]), 3, "review")
    assert active_review.value.status == 409
    schedule = service.save_schedule(
        context_a,
        UUID(plan["id"]),
        None,
        None,
        {
            "local_time": local_time(8, 30),
            "timezone": "Asia/Shanghai",
            "rrule": "FREQ=DAILY",
            "valid_from": start_date,
            "valid_to": None,
            "enabled": True,
        },
        "f06-schedule-0001",
    )
    schedule_snapshot = dict(schedule)
    updated_schedule = service.save_schedule(
        context_a,
        None,
        UUID(schedule["id"]),
        1,
        {
            "local_time": local_time(9, 15),
            "timezone": "Asia/Shanghai",
            "rrule": "FREQ=DAILY",
            "valid_from": start_date,
            "valid_to": None,
            "enabled": True,
        },
    )
    assert updated_schedule["record_version"] == 2
    assert (
        service.save_schedule(
            context_a,
            UUID(plan["id"]),
            None,
            None,
            {
                "local_time": local_time(8, 30),
                "timezone": "Asia/Shanghai",
                "rrule": "FREQ=DAILY",
                "valid_from": start_date,
                "valid_to": None,
                "enabled": True,
            },
            "f06-schedule-0001",
        )
        == schedule_snapshot
    )
    with pytest.raises(Problem) as schedule_conflict:
        service.save_schedule(
            context_a,
            UUID(plan["id"]),
            None,
            None,
            {
                "local_time": local_time(8, 31),
                "timezone": "Asia/Shanghai",
                "rrule": "FREQ=DAILY",
                "valid_from": start_date,
                "valid_to": None,
                "enabled": True,
            },
            "f06-schedule-0001",
        )
    assert schedule_conflict.value.code == "IDEMPOTENCY_CONFLICT"
    assert (
        service.create_plan(
            context_a,
            {
                "medication_name": "synthetic-plan",
                "source_type": "manual",
                "source_document_id": None,
                "dosage_text": None,
                "route_code": None,
                "start_date": start_date,
                "end_date": start_date + timedelta(days=10),
            },
            "f06-idempotency-0001",
        )
        == plan
    )
    with app_engine.connect() as connection:
        connection.execute(
            text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_a)}
        )
        persisted = connection.execute(
            text("""SELECT response_status, response_snapshot
                FROM health.medication_idempotency
                WHERE patient_id = :patient_id AND route = :route AND idempotency_key = :key"""),
            {
                "patient_id": patient_a,
                "route": "POST:/medication-plans",
                "key": "f06-idempotency-0001",
            },
        ).one()
        assert persisted.response_status == 201
        assert persisted.response_snapshot["plan_status"] == "discontinued"
    assert service.get_plan(context_a, UUID(plan["id"]))["plan_status"] == "active"
    assert service.get_plan(context_a, UUID(plan["id"]))["confirmation_status"] == "confirmed"
    assert service.list_schedules(context_a, UUID(plan["id"]))[0]["enabled"] is True
    with pytest.raises(Problem) as forbidden:
        service.get_plan(context_b, UUID(plan["id"]))
    assert forbidden.value.status == 404
    with app_engine.connect() as connection:
        flags = connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'health.medication_checkin'::regclass"
            )
        ).one()
        assert flags.relrowsecurity and flags.relforcerowsecurity
        fk_count = connection.scalar(
            text(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = "
                "'health.medication_checkin'::regclass AND contype = 'f'"
            )
        )
        assert fk_count >= 1
    worker_password = os.environ.get("GUTCARE_TEST_WORKER_PASSWORD")
    if not worker_password:
        pytest.skip("Set GUTCARE_TEST_WORKER_PASSWORD to verify the dedicated worker role.")
    worker_url = _integration_urls()[0].set(username="gutcare_worker", password=worker_password)
    worker_engine = _engine(worker_url, "gutcare-pg18-medication-worker")
    try:
        worker_sessions = _sessions(worker_engine)
        with worker_engine.connect() as worker_connection:
            worker_plan_count = worker_connection.scalar(
                text("SELECT count(*) FROM health.medication_plan WHERE plan_status = 'active'")
            )
            worker_schedule_count = worker_connection.scalar(
                text("SELECT count(*) FROM health.medication_schedule WHERE enabled")
            )
            schedule_values = worker_connection.execute(
                text(
                    "SELECT valid_from, valid_to, rrule, local_time "
                    "FROM health.medication_schedule WHERE id = :id"
                ),
                {"id": UUID(schedule["id"])},
            ).one()
        assert worker_plan_count and worker_schedule_count
        assert schedule_values.valid_from == start_date
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(lambda _: materialize(worker_sessions, today=start_date), range(2))
            )
        assert sum(outcomes) >= 1
        assert materialize(worker_sessions, today=start_date) == 0
        checkins = service.list_checkins(context_a, start_date, start_date + timedelta(days=13))
        assert checkins
        answered = service.update_checkin(
            context_a,
            UUID(checkins[0]["id"]),
            checkins[0]["record_version"],
            {"status": "not_taken", "taken_at": None, "note": "synthetic"},
        )
        service.update_checkin(
            context_a,
            UUID(checkins[1]["id"]),
            checkins[1]["record_version"],
            {"status": "taken", "taken_at": utc_now(), "note": None},
        )
        service.update_checkin(
            context_a,
            UUID(checkins[2]["id"]),
            checkins[2]["record_version"],
            {"status": "skipped", "taken_at": None, "note": None},
        )
        before_response_time = answered["scheduled_for"]
        service.patch_plan(
            context_a,
            UUID(plan["id"]),
            3,
            {"end_date": start_date + timedelta(days=5)},
        )
        plan_changed_rows = service.list_checkins(
            context_a, start_date, start_date + timedelta(days=13)
        )
        assert all(
            row["status"] != "pending"
            or date.fromisoformat(row["local_date"]) <= start_date + timedelta(days=5)
            for row in plan_changed_rows
        )
        pending_before = {
            row["id"]: row["scheduled_for"]
            for row in plan_changed_rows
            if row["status"] == "pending"
        }
        current_schedule = service.list_schedules(context_a, UUID(plan["id"]))[0]
        service.save_schedule(
            context_a,
            None,
            UUID(schedule["id"]),
            current_schedule["record_version"],
            {
                "local_time": local_time(10, 0),
                "timezone": "Asia/Tokyo",
                "rrule": "FREQ=DAILY",
                "valid_from": start_date,
                "valid_to": None,
                "enabled": True,
            },
        )
        after = service.list_checkins(context_a, start_date, start_date + timedelta(days=13))
        answered_after = next(row for row in after if row["id"] == answered["id"])
        assert answered_after["status"] == "not_taken"
        assert answered_after["scheduled_for"] == before_response_time
        pending_after = {
            row["id"]: row["scheduled_for"] for row in after if row["status"] == "pending"
        }
        assert any(pending_before[item] != pending_after[item] for item in pending_after)
        assert any(
            row["status"] == "pending" and row["scheduled_for"].startswith("202") for row in after
        )
        assert schedule["enabled"] is True
    finally:
        worker_engine.dispose()


def test_f08_postgres18_snapshot_idempotency_rls_and_immutability(database: Any) -> None:
    """T66-T67: F08 snapshots are patient scoped, confirmed-only and immutable."""
    app_engine, _migrator_engine = database
    user_a, patient_a = _seed_patient(app_engine, nickname="f08-a")
    user_b, patient_b = _seed_patient(app_engine, nickname="f08-b")
    with _sessions(app_engine).begin() as db:
        for patient_id in (patient_a, patient_b):
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"),
                {"value": str(patient_id)},
            )
            db.add(
                PatientConsent(
                    patient_id=patient_id,
                    consent_type="third_party_ai",
                    document_version="test-v1",
                    granted=True,
                    decided_at=utc_now(),
                    metadata_json={"notice_summary_hash": "1" * 64},
                )
            )
            db.add(
                DietRecord(
                    patient_id=patient_id,
                    occurred_at=utc_now(),
                    meal_type="lunch",
                    text_description="must not enter snapshot",
                    payload={"items": [{"name": "rice"}], "private_note": "exclude"},
                    confirmation_status="confirmed",
                    record_version=1,
                )
            )
    service = AnalysisService(_sessions(app_engine))
    context_a = AuthContext(user_id=user_a, session_id=uuid4())
    payload = {
        "analysis_type": "comprehensive_health_analysis",
        "requested_from": None,
        "requested_to": None,
    }
    first, replayed = service.create(context_a, payload, "f08-idempotency-0001")
    replay, is_replay = service.create(context_a, payload, "f08-idempotency-0001")
    assert not replayed and is_replay and replay == first
    same_key_barrier = Barrier(2)

    def same_key_create(_: int) -> tuple[dict[str, Any], bool]:
        same_key_barrier.wait(timeout=5)
        return service.create(context_a, payload, "f08-idempotency-concurrent-01")

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_replays = list(executor.map(same_key_create, range(2)))
    assert concurrent_replays[0][0] == concurrent_replays[1][0]
    assert sorted(replayed for _, replayed in concurrent_replays) == [False, True]
    with _sessions(app_engine).begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :value, true)"),
            {"value": str(patient_a)},
        )
        created_count = db.scalar(
            text(
                "SELECT count(*) FROM analysis.analysis_task_idempotency "
                "WHERE patient_id=:patient AND idempotency_key=:key"
            ),
            {"patient": patient_a, "key": "f08-idempotency-concurrent-01"},
        )
        assert created_count == 1

    api_app = FastAPI()
    api_app.state.analysis_service = service
    api_app.include_router(analysis_router)
    api_app.dependency_overrides[current_auth_context] = lambda: context_a
    api_client = TestClient(api_app)
    response_barrier = Barrier(2)

    def concurrent_http_create(_: int) -> Any:
        response_barrier.wait(timeout=5)
        return api_client.post(
            "/api/v1/analysis-tasks",
            json=payload,
            headers={"Idempotency-Key": "f08-api-concurrent-202"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        http_responses = list(executor.map(concurrent_http_create, range(2)))
    assert [response.status_code for response in http_responses] == [202, 202]
    assert http_responses[0].json() == http_responses[1].json()
    assert http_responses[0].headers["location"] == http_responses[1].headers["location"]

    conflict_barrier = Barrier(2)

    def conflicting_create(changed: bool) -> tuple[str, dict[str, Any] | None]:
        conflict_barrier.wait(timeout=5)
        body = {**payload, "analysis_type": "periodic_summary"} if changed else payload
        try:
            value, _ = service.create(context_a, body, "f08-idempotency-concurrent-02")
            return "created", value
        except Problem as exc:
            return exc.code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        conflict_outcomes = list(executor.map(conflicting_create, (False, True)))
    assert sorted(outcome for outcome, _ in conflict_outcomes) == [
        "IDEMPOTENCY_CONFLICT",
        "created",
    ]
    with pytest.raises(Problem) as mismatch:
        service.create(
            context_a, {**payload, "analysis_type": "periodic_summary"}, "f08-idempotency-0001"
        )
    assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(Problem) as cross_patient:
        service.get(AuthContext(user_id=user_b, session_id=uuid4()), UUID(first["id"]))
    assert cross_patient.value.status == 404
    with _sessions(app_engine).begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :value, true)"), {"value": str(patient_a)}
        )
        snapshot = db.get(TaskInputSnapshot, UUID(first["id"]))
        assert snapshot is not None
        original_hash = snapshot.content_hash
        assert "text_description" not in json.dumps(snapshot.snapshot_payload)
        assert "private_note" not in json.dumps(snapshot.snapshot_payload)
    with pytest.raises(DBAPIError):
        with _sessions(app_engine).begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"), {"value": str(patient_a)}
            )
            db.execute(
                text(
                    "UPDATE analysis.task_input_snapshot SET content_hash = :hash "
                    "WHERE task_id = :id"
                ),
                {"hash": "0" * 64, "id": first["id"]},
            )
    with _sessions(app_engine).begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :value, true)"), {"value": str(patient_a)}
        )
        unchanged = db.get(TaskInputSnapshot, UUID(first["id"]))
        assert unchanged is not None and unchanged.content_hash == original_hash


def test_f08_t68_t71_worker_lifecycle_and_snapshot_boundaries(database: Any) -> None:
    """T68-T71: real PG worker isolation, lease recovery, callback, retry and cancellation."""
    app_engine, migrator_engine = database
    # This integration fixture shares one disposable database across cases. Clear
    # prior lifecycle fixtures so the two claims below race over exactly one row.
    with migrator_engine.begin() as db:
        db.execute(text("TRUNCATE analysis.analysis_task CASCADE"))
    worker_raw = os.environ.get("GUTCARE_TEST_ANALYSIS_WORKER_DATABASE_URL")
    if not worker_raw:
        pytest.skip("Set GUTCARE_TEST_ANALYSIS_WORKER_DATABASE_URL for F08 worker gates.")
    worker_engine = _engine(make_url(worker_raw), "gutcare-pg18-analysis-worker")
    user, patient = _seed_patient(app_engine, nickname="f08-t68")
    context = AuthContext(user_id=user, session_id=uuid4())
    fact_id, candidate_id, request_id = uuid4(), uuid4(), uuid4()
    document_id, file_id = uuid4(), uuid4()
    stool_id, symptom_id = uuid4(), uuid4()
    medication_id, schedule_id, checkin_id = uuid4(), uuid4(), uuid4()
    rule_id, alert_id = uuid4(), uuid4()
    with _sessions(migrator_engine).begin() as db:
        db.add(
            RiskRule(
                id=rule_id,
                rule_code=f"f08-test-{rule_id}",
                version=1,
                severity="attention",
                condition_json={"test_only": True},
                message="synthetic rule",
                recommended_action="review synthetic data",
                review_status="approved",
                environment="test_only",
            )
        )
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        db.add(
            PatientConsent(
                patient_id=patient,
                consent_type="third_party_ai",
                document_version="t-v1",
                granted=True,
                decided_at=utc_now(),
                metadata_json={"notice_summary_hash": "2" * 64},
            )
        )
        db.add(
            DietRecord(
                patient_id=patient,
                occurred_at=utc_now(),
                meal_type="lunch",
                text_description="never sent",
                payload={"private_note": "never sent"},
                confirmation_status="confirmed",
                record_version=4,
            )
        )
        db.add(
            StoolRecord(
                id=stool_id,
                patient_id=patient,
                occurred_at=utc_now(),
                bristol_type=4,
                confirmation_status="confirmed",
                record_version=2,
            )
        )
        db.add(
            SymptomRecord(
                id=symptom_id,
                patient_id=patient,
                occurred_at=utc_now(),
                symptom_status="ongoing",
                record_version=3,
            )
        )
        db.flush()
        db.add(
            SymptomItem(
                patient_id=patient,
                symptom_record_id=symptom_id,
                symptom_code="bloating",
                severity=2,
                patient_confirmed=True,
            )
        )
        db.add(
            FileObject(
                id=file_id,
                patient_id=patient,
                bucket_name="f08-tests",
                object_key=f"{file_id}.pdf",
                original_name="synthetic.pdf",
                content_type="application/pdf",
                size_bytes=1,
                content_sha256="a" * 64,
                sensitivity="medical",
                scan_status="clean",
                storage_status="available",
            )
        )
        db.add(
            MedicalDocument(
                id=document_id,
                patient_id=patient,
                file_object_id=file_id,
                document_type="lab_report",
                processing_mode="analyze",
                parse_status="confirmed",
                record_version=1,
            )
        )
        db.flush()
        db.add(
            MedicalParseRequest(
                id=request_id,
                patient_id=patient,
                document_id=document_id,
                file_object_id=file_id,
                record_version=1,
                status="succeeded",
            )
        )
        db.flush()
        db.add(
            MedicalFieldCandidate(
                id=candidate_id,
                patient_id=patient,
                request_id=request_id,
                field_code="weight_kg",
                value_type="decimal",
                value=60,
                source_locator={"page": 1},
                review_status="accepted",
                record_version=1,
            )
        )
        db.flush()
        db.add(
            ConfirmedMedicalFact(
                id=fact_id,
                patient_id=patient,
                candidate_id=candidate_id,
                field_code="weight_kg",
                value_type="decimal",
                value=60,
                fact_status="active",
            )
        )
        db.add(
            MedicationPlan(
                id=medication_id,
                patient_id=patient,
                medication_name="synthetic medication",
                source_type="manual",
                confirmation_status="confirmed",
                plan_status="active",
                record_version=1,
            )
        )
        db.flush()
        db.add(
            MedicationSchedule(
                id=schedule_id,
                plan_id=medication_id,
                patient_id=patient,
                local_time=local_time(8, 0),
                timezone="Asia/Shanghai",
                rrule="FREQ=DAILY",
                valid_from=date.today(),
                enabled=True,
                record_version=1,
            )
        )
        db.flush()
        db.add(
            MedicationCheckin(
                id=checkin_id,
                schedule_id=schedule_id,
                patient_id=patient,
                local_date=date.today(),
                scheduled_for=utc_now(),
                status="taken",
                taken_at=utc_now(),
                record_version=1,
            )
        )
        db.flush()
        diet_source = db.scalar(select(DietRecord).where(DietRecord.patient_id == patient))
        assert diet_source is not None
        db.add(
            RiskAlert(
                id=alert_id,
                patient_id=patient,
                rule_id=rule_id,
                source_record_id=diet_source.id,
                source_record_version=diet_source.record_version,
                severity="attention",
                message="synthetic alert",
                recommended_action="review synthetic data",
                deduplication_key=f"f08-{alert_id}",
                evidence_summary={"record_type": "diet_record"},
            )
        )
    patient_service = AnalysisService(_sessions(app_engine))
    worker = AnalysisService(_sessions(worker_engine))
    created, _ = patient_service.create(
        context,
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": None,
            "requested_to": None,
        },
        "f08-worker-create-001",
    )
    task_id = UUID(created["id"])

    # T68: one pending task can only be claimed once; expired lease is recoverable.
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: worker.claim(), range(2)))
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1 and claimed[0]["task_id"] == str(task_id)
    inputs = worker.inputs(task_id)
    encoded = json.dumps(inputs)
    assert (
        "never sent" not in encoded and "private_note" not in encoded and "file_url" not in encoded
    )
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        source_row = db.scalar(select(DietRecord).where(DietRecord.patient_id == patient))
        assert source_row is not None
        source_row.meal_type = "dinner"
        source_row.text_description = "changed after snapshot"
        source_row.record_version += 1
    assert worker.inputs(task_id)["snapshot_hash"] == inputs["snapshot_hash"]
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        task = db.get(AnalysisTask, task_id)
        assert task is not None
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
    assert worker.claim()["task_id"] == str(task_id)
    with pytest.raises(DBAPIError):
        with worker_engine.begin() as db:
            db.execute(text("SELECT * FROM health.diet_record LIMIT 1"))
    with pytest.raises(DBAPIError):
        with worker_engine.begin() as db:
            db.execute(text("UPDATE health.diet_record SET meal_type = 'dinner'"))

    # T69: exact snapshot evidence accepted once; callback idempotent; foreign refs rejected.
    snapshot_evidence = [
        {
            "source_type": record["record_type"],
            "source_id": record["record_id"],
            "source_version": record["record_version"],
            "locator": record["locator"],
        }
        for record in inputs["records"]
    ]
    callback_id = uuid4()
    result = {
        "status": "succeeded",
        "schema_version": "1.0",
        "summary": "观察摘要",
        "observations": ["有已确认饮食记录"],
        "evidence": snapshot_evidence,
        "uncertainties": [],
        "missing_data": [],
    }
    invalid_result = {**result, "evidence": [{**result["evidence"][0], "source_id": str(uuid4())}]}
    with pytest.raises(Problem) as foreign_evidence:
        worker.result(task_id, uuid4(), invalid_result)
    assert foreign_evidence.value.code == "INVALID_EVIDENCE"
    worker.result(task_id, callback_id, result)
    worker.result(task_id, callback_id, result)
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        for source in db.scalars(select(DietRecord).where(DietRecord.patient_id == patient)):
            source.deleted_at = utc_now()
        for model, source_id in (
            (StoolRecord, stool_id),
            (SymptomRecord, symptom_id),
            (MedicalDocument, document_id),
            (FileObject, file_id),
            (MedicationPlan, medication_id),
            (MedicationSchedule, schedule_id),
        ):
            source = db.get(model, source_id)
            assert source is not None
            source.deleted_at = utc_now()
        file_object = db.get(FileObject, file_id)
        assert file_object is not None
        file_object.storage_status = "deleted"
        fact = db.get(ConfirmedMedicalFact, fact_id)
        assert fact is not None
        fact.fact_status = "source_deleted"
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        frozen_after_source_deletion = db.get(TaskInputSnapshot, task_id)
        assert frozen_after_source_deletion is not None
        assert frozen_after_source_deletion.content_hash == inputs["snapshot_hash"]
    projected = patient_service.get(context, task_id)
    projected_evidence = projected["result"]["evidence"]
    assert {item["source_type"] for item in projected_evidence} >= {
        "confirmed_medical_fact",
        "diet_record",
        "stool_record",
        "symptom_record",
        "medication_plan",
        "medication_checkin",
        "risk_alert",
    }
    assert all(
        item["source_deleted"] is True and item["locator"] is None for item in projected_evidence
    )
    listed_task = next(item for item in patient_service.list(context) if item["id"] == str(task_id))
    assert all(
        item["source_deleted"] is True and item["locator"] is None
        for item in listed_task["result"]["evidence"]
    )
    with pytest.raises(Problem) as late:
        worker.fail(task_id, uuid4(), "AGENT_TIMEOUT")
    assert late.value.status == 409

    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        db.add(
            DietRecord(
                patient_id=patient,
                occurred_at=utc_now(),
                meal_type="breakfast",
                confirmation_status="confirmed",
                record_version=1,
            )
        )

    failed, _ = patient_service.create(
        context,
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": None,
            "requested_to": None,
        },
        "f08-worker-create-002",
    )
    failed_id = UUID(failed["id"])
    assert worker.claim()["task_id"] == str(failed_id)
    worker.fail(failed_id, uuid4(), "AGENT_UNAVAILABLE")
    retried, _ = patient_service.retry(context, failed_id, "f08-worker-retry-001")
    assert retried["attempt"] == 2
    with pytest.raises(Problem):
        patient_service.retry(context, failed_id, "f08-worker-retry-002")
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient)})
        retry_task = db.get(AnalysisTask, UUID(retried["id"]))
        assert retry_task is not None and retry_task.retry_of == failed_id
        original_snapshot = db.get(TaskInputSnapshot, failed_id)
        retried_snapshot = db.get(TaskInputSnapshot, retry_task.id)
        assert original_snapshot is not None and retried_snapshot is not None
        assert retried_snapshot.content_hash == original_snapshot.content_hash
    retry_id = UUID(retried["id"])
    assert worker.claim()["task_id"] == str(retry_id)
    worker.fail(retry_id, uuid4(), "AGENT_UNAVAILABLE")

    # T70: cancellation and result submission race on independent DB sessions.
    cancelled, _ = patient_service.create(
        context,
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": None,
            "requested_to": None,
        },
        "f08-worker-create-003",
    )
    cancelled_id = UUID(cancelled["id"])
    assert worker.claim()["task_id"] == str(cancelled_id)
    cancel_inputs = worker.inputs(cancelled_id)
    race_result = {
        **result,
        "evidence": [
            {
                "source_type": item["record_type"],
                "source_id": item["record_id"],
                "source_version": item["record_version"],
                "locator": item["locator"],
            }
            for item in cancel_inputs["records"][:1]
        ],
    }
    race_barrier = Barrier(2)

    def race_cancel() -> str:
        race_barrier.wait(timeout=5)
        try:
            patient_service.cancel(context, cancelled_id)
            return "cancelled"
        except Problem as exc:
            return exc.code

    def race_submit() -> str:
        race_barrier.wait(timeout=5)
        try:
            worker.result(cancelled_id, uuid4(), race_result)
            return "succeeded"
        except Problem as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        race_outcomes = [executor.submit(race_cancel), executor.submit(race_submit)]
        outcomes = [item.result(timeout=10) for item in race_outcomes]
    final_task = patient_service.get(context, cancelled_id)
    assert final_task["status"] in {"cancelled", "succeeded"}
    assert sum(value in {"cancelled", "succeeded"} for value in outcomes) == 1
    with migrator_engine.begin() as db:
        db.execute(
            text("SELECT set_config('app.patient_id', :patient, true)"),
            {"patient": str(patient)},
        )
        callback_count = db.scalar(
            text("SELECT count(*) FROM analysis.analysis_task_callback WHERE task_id=:task"),
            {"task": cancelled_id},
        )
    assert callback_count == (1 if final_task["status"] == "succeeded" else 0), (
        callback_count,
        final_task["status"],
        outcomes,
        cancelled_id,
    )

    # T71: worker has F08-only privileges; Agent availability is not required for creation.
    pending, _ = patient_service.create(
        context,
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": None,
            "requested_to": None,
        },
        "f08-worker-create-004",
    )
    assert pending["status"] == "pending"
    assert patient_service.list(context)
    consent_service = AuthService(
        Settings(
            env="test",
            jwt_signing_key="integration-only-signing-key-000000000000000000000000",
            jwt_issuer="gutcare-business-api",
            jwt_audience="gutcare-mobile-app",
            third_party_ai_policy_version="third_party_ai-v1",
            third_party_ai_summary_hash="0" * 64,
        ),
        _sessions(app_engine),
    )
    consent_service.record_consent(context, "third_party_ai", "third_party_ai-v1", False)
    assert patient_service.get(context, UUID(pending["id"]))["status"] == "cancelled"
    with pytest.raises(Problem) as revoked_input:
        worker.inputs(UUID(pending["id"]))
    assert revoked_input.value.status in {404, 409}
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :id, true)"), {"id": str(user)})
        account = db.get(UserAccount, user)
        assert account is not None
        account.status = "locked"
    with pytest.raises(Problem) as frozen_account:
        patient_service.create(
            context,
            {
                "analysis_type": "comprehensive_health_analysis",
                "requested_from": None,
                "requested_to": None,
            },
            "f08-worker-create-after-freeze",
        )
    assert frozen_account.value.status == 401
    worker_engine.dispose()


def test_f09_postgres18_callback_feedback_projection_and_isolation(database: Any) -> None:
    """Run F09 last so its persisted rows are present in the restore rehearsal."""
    _f09_postgres18_callback_feedback_projection_and_isolation(database)


def test_f12_postgres18_outbox_api_preferences_and_worker(database: Any) -> None:
    """T80-T86: transactional source mapping, payload privacy, RLS and dispatch recovery base."""
    app_engine, migrator_engine = database
    worker_raw = os.environ.get("GUTCARE_TEST_NOTIFICATION_WORKER_DATABASE_URL")
    if not worker_raw:
        pytest.skip("Set GUTCARE_TEST_NOTIFICATION_WORKER_DATABASE_URL for F12 worker gates.")
    worker_url = make_url(worker_raw)
    if (
        worker_url.database != _DATABASE_NAME
        or worker_url.username != "gutcare_notification_worker"
    ):
        pytest.fail(
            "Notification worker URL must target the dedicated PG18 test DB as its isolated role."
        )
    worker_engine = _engine(worker_url, "gutcare-pg18-notification-worker")
    # Clear pending work left by earlier tests through the worker's global UPDATE policy.
    with _sessions(worker_engine).begin() as db:
        db.execute(
            text(
                "UPDATE health.notification_outbox SET status='dispatched', lease_expires_at=NULL WHERE status IN ('pending','processing')"
            )
        )
    user, patient = _seed_patient(app_engine, nickname="f12-patient")
    other_user, _other_patient = _seed_patient(app_engine, nickname="f12-other")
    context = AuthContext(user_id=user, session_id=uuid4())
    other_context = AuthContext(user_id=other_user, session_id=uuid4())
    task_id, advice_id, alert_id, checkin_id = (uuid4() for _ in range(4))
    other_task_id = uuid4()
    schedule_id, plan_id, rule_id = (uuid4() for _ in range(3))
    local_day = date.today() + timedelta(days=1)

    # Seed four domain events through their owning tables. The notification outbox
    # trigger is part of each source transaction and never receives source content.
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(other_user)})
        db.execute(
            text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(_other_patient)}
        )
        db.execute(
            text(
                "INSERT INTO analysis.analysis_task(id,patient_id,analysis_type,status) VALUES (:id,:p,'periodic_summary','failed')"
            ),
            {"id": other_task_id, "p": _other_patient},
        )
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.add(
            AnalysisTask(
                id=task_id,
                patient_id=patient,
                analysis_type="comprehensive_health_analysis",
                status="pending",
            )
        )
        db.flush()
        db.execute(
            text(
                "UPDATE analysis.analysis_task SET status='partial', updated_at=now() WHERE id=:id"
            ),
            {"id": task_id},
        )
        db.execute(
            text("""
            INSERT INTO analysis.health_advice
              (id,patient_id,task_id,category,priority,title,body,uncertainty,applicability,safety_boundary,version)
            VALUES (:id,:p,:task,'diet','routine','sensitive title','sensitive advice body',
              jsonb_build_object('level','low','reasons','[]'::jsonb),
              jsonb_build_object('scope','general','limitations','[]'::jsonb),
              jsonb_build_object('not_diagnosis',true,'not_prescription',true,'risk_alert_priority',true),'1.0')
        """),
            {"id": advice_id, "p": patient, "task": task_id},
        )
        db.execute(
            text("""
            INSERT INTO health.medication_plan(id,patient_id,medication_name,source_type,confirmation_status,plan_status)
            VALUES (:id,:p,'sensitive medication','manual','confirmed','active')
        """),
            {"id": plan_id, "p": patient},
        )
        db.execute(
            text("""
            INSERT INTO health.medication_schedule(id,plan_id,patient_id,local_time,timezone,rrule,valid_from)
            VALUES (:id,:plan,:p,'08:00','Asia/Shanghai','FREQ=DAILY',:day)
        """),
            {"id": schedule_id, "plan": plan_id, "p": patient, "day": local_day},
        )
        db.execute(
            text("""
            INSERT INTO health.medication_checkin(id,schedule_id,patient_id,local_date,scheduled_for,status)
            VALUES (:id,:schedule,:p,:day,now(),'pending')
        """),
            {"id": checkin_id, "schedule": schedule_id, "p": patient, "day": local_day},
        )
    with _sessions(migrator_engine).begin() as db:
        db.execute(
            text("""
            INSERT INTO safety.risk_rule(id,rule_code,version,severity,condition_json,message,recommended_action,review_status,environment)
            VALUES (:id,'f12-synthetic',1,'attention','{}'::jsonb,'sensitive risk message','sensitive action','draft','test_only')
        """),
            {"id": rule_id},
        )
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.execute(
            text("""
            INSERT INTO safety.risk_alert(id,patient_id,rule_id,source_record_id,source_record_version,severity,message,recommended_action,deduplication_key,evidence_summary)
            VALUES (:id,:p,:rule,:source,1,'attention','sensitive risk message','sensitive action','f12-risk-once','{}'::jsonb)
        """),
            {"id": alert_id, "p": patient, "rule": rule_id, "source": uuid4()},
        )

    with _sessions(worker_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        events = (
            db.execute(
                text(
                    "SELECT event_type,target_type,target_id,priority,deduplication_key,payload FROM health.notification_outbox WHERE patient_id=:p ORDER BY event_type"
                ),
                {"p": patient},
            )
            .mappings()
            .all()
        )
        assert {e["event_type"] for e in events} == {
            "analysis_completed",
            "advice_created",
            "risk_alert_created",
            "checkin_reminder",
        }
        assert all(
            set(e["payload"])
            == {
                "event_type",
                "patient_id",
                "target_type",
                "target_id",
                "occurred_at",
                "priority",
                "deduplication_key",
            }
            for e in events
        )
        assert not any(
            any(
                word in json.dumps(e["payload"]).lower()
                for word in ("sensitive", "medication_name", "body", "url", "locator", "prompt")
            )
            for e in events
        )
        checkin_event = next(e for e in events if e["event_type"] == "checkin_reminder")
        assert checkin_event["target_id"] == checkin_id
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text(
                        "UPDATE health.notification_outbox SET payload=payload||'{\"body\":\"forbidden\"}'::jsonb WHERE patient_id=:p AND event_type='risk_alert_created'"
                    ),
                    {"p": patient},
                )
        db.execute(
            text(
                "UPDATE health.notification_outbox SET status='processing', lease_expires_at=now()-interval '1 second' WHERE patient_id=:p AND event_type='checkin_reminder'"
            ),
            {"p": patient},
        )

    with ThreadPoolExecutor(max_workers=2) as dispatchers:
        claims = list(
            dispatchers.map(lambda _: dispatch_batch(_sessions(worker_engine), 1), range(2))
        )
    assert sum(claims) == 2
    with _sessions(worker_engine).begin() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM health.notification_outbox WHERE attempts=1 AND status='dispatched'"
                )
            )
            == 2
        )
    assert dispatch_batch(_sessions(worker_engine), 3) == 3
    with _sessions(worker_engine).begin() as db:
        attempts = (
            db.execute(
                text("SELECT attempts FROM health.notification_outbox WHERE patient_id=:p"),
                {"p": patient},
            )
            .scalars()
            .all()
        )
    assert sorted(attempts) == [1, 1, 1, 1]
    notifications = NotificationService(_sessions(app_engine))
    page = notifications.list_notifications(context, 100, None, None, False)
    assert len(page["items"]) == 4
    page_one = notifications.list_notifications(context, 2, None, None, False)
    assert len(page_one["items"]) == 2 and page_one["next_cursor"]
    page_two = notifications.list_notifications(context, 2, page_one["next_cursor"], None, False)
    page_ids = [item["id"] for item in page_one["items"] + page_two["items"]]
    assert len(page_two["items"]) == 2 and len(set(page_ids)) == 4
    with pytest.raises(Problem) as invalid_cursor:
        notifications.list_notifications(context, 2, "not-a-valid-cursor", None, False)
    assert invalid_cursor.value.status == 400
    risk_item = next(item for item in page["items"] if item["category"] == "risk")
    assert risk_item["priority"] == "risk" and risk_item["target"]["type"] == "risk_alert"
    assert "body" not in risk_item and "message" not in risk_item
    with pytest.raises(Problem) as isolated:
        notifications.get(other_context, UUID(page["items"][0]["id"]))
    assert isolated.value.status == 404
    assert notifications.unread_count(context) == {"count": 4}
    read_id = UUID(page["items"][0]["id"])
    notifications.mark_read(context, read_id)
    notifications.mark_read(context, read_id)
    assert notifications.unread_count(context) == {"count": 3}
    batch_ids = [UUID(item["id"]) for item in page["items"][:2]]
    with ThreadPoolExecutor(max_workers=2) as readers:
        batch_results = list(
            readers.map(lambda _: notifications.mark_many(context, batch_ids), range(2))
        )
    assert all(len(result) == 2 for result in batch_results)
    assert notifications.unread_count(context) == {"count": 2}
    with pytest.raises(Problem) as cross_patient_batch:
        notifications.mark_many(other_context, [UUID(page["items"][0]["id"])])
    assert cross_patient_batch.value.status == 404
    assert dispatch_batch(_sessions(worker_engine), 20, patient_id=patient) == 0
    advice_item = next(item for item in page["items"] if item["category"] == "advice")
    with _sessions(migrator_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.execute(
            text("DELETE FROM analysis.health_advice WHERE id=:id AND patient_id=:p"),
            {"id": advice_id, "p": patient},
        )
    unavailable = notifications.get(context, UUID(advice_item["id"]))
    assert unavailable["target_unavailable"] is True and unavailable["target"] is None

    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
    preferences = {
        "ordinary_in_app_enabled": False,
        "quiet_start": None,
        "quiet_end": None,
        "timezone": "UTC",
    }
    notifications.set_preferences(context, preferences)
    suppressed_task = uuid4()
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.execute(
            text(
                "INSERT INTO analysis.analysis_task(id,patient_id,analysis_type,status) VALUES (:id,:p,'periodic_summary','failed')"
            ),
            {"id": suppressed_task, "p": patient},
        )
    assert dispatch_batch(_sessions(worker_engine), 20, patient_id=patient) == 0
    with _sessions(worker_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        suppressed = db.scalar(
            text(
                "SELECT status FROM health.notification_outbox WHERE patient_id=:p AND target_id=:id"
            ),
            {"p": patient, "id": suppressed_task},
        )
    assert suppressed == "suppressed"

    risk_bypass_id = uuid4()
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.execute(
            text(
                "INSERT INTO safety.risk_alert(id,patient_id,rule_id,source_record_id,source_record_version,severity,message,recommended_action,deduplication_key,evidence_summary) VALUES (:id,:p,:rule,:src,1,'attention','private risk','private action','risk-bypass','{}'::jsonb)"
            ),
            {"id": risk_bypass_id, "p": patient, "rule": rule_id, "src": uuid4()},
        )
    assert dispatch_batch(_sessions(worker_engine), 5, patient_id=patient) == 1
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        risk_status = db.scalar(
            text("SELECT status FROM safety.risk_alert WHERE id=:id"), {"id": risk_bypass_id}
        )
    assert risk_status == "unread"
    risk_page = notifications.list_notifications(context, 100, None, "risk", False)
    assert any(item["target"]["id"] == str(risk_bypass_id) for item in risk_page["items"])

    dead_target = uuid4()
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        db.execute(
            text(
                "INSERT INTO safety.risk_alert(id,patient_id,rule_id,source_record_id,source_record_version,severity,message,recommended_action,deduplication_key,evidence_summary) VALUES (:id,:p,:rule,:src,1,'attention','private risk','private action','risk-dead-letter','{}'::jsonb)"
            ),
            {"id": dead_target, "p": patient, "rule": rule_id, "src": uuid4()},
        )
    with _sessions(migrator_engine).begin() as db:
        db.execute(
            text(
                "CREATE FUNCTION health.f12_injected_dispatch_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.target_id='"
                + str(dead_target)
                + "'::uuid THEN RAISE EXCEPTION 'test-only dispatch failure'; END IF; RETURN NEW; END $$"
            )
        )
        db.execute(
            text(
                "CREATE TRIGGER f12_injected_dispatch_failure BEFORE INSERT ON health.patient_notification FOR EACH ROW EXECUTE FUNCTION health.f12_injected_dispatch_failure()"
            )
        )
    try:
        for expected_attempt in range(1, 9):
            assert dispatch_batch(_sessions(worker_engine), 1, patient_id=patient) == 0
            with _sessions(worker_engine).begin() as db:
                db.execute(
                    text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)}
                )
                row = db.execute(
                    text(
                        "SELECT status,attempts FROM health.notification_outbox WHERE patient_id=:p AND target_id=:id"
                    ),
                    {"p": patient, "id": dead_target},
                ).one()
                assert row.attempts == expected_attempt
                if expected_attempt < 8:
                    assert row.status == "pending"
                    db.execute(
                        text(
                            "UPDATE health.notification_outbox SET available_at=now() WHERE patient_id=:p AND target_id=:id"
                        ),
                        {"p": patient, "id": dead_target},
                    )
                else:
                    assert row.status == "dead_letter"
    finally:
        with _sessions(migrator_engine).begin() as db:
            db.execute(
                text(
                    "DROP TRIGGER IF EXISTS f12_injected_dispatch_failure ON health.patient_notification"
                )
            )
            db.execute(text("DROP FUNCTION IF EXISTS health.f12_injected_dispatch_failure()"))

    with migrator_engine.connect() as db:
        privileges = db.execute(
            text("""
            SELECT has_table_privilege('gutcare_notification_worker','health.notification_outbox','SELECT,UPDATE'),
                   has_table_privilege('gutcare_notification_worker','health.notification_outbox','INSERT'),
                   has_table_privilege('gutcare_notification_worker','analysis.health_advice','SELECT'),
                   has_table_privilege('gutcare_notification_worker','safety.risk_alert','SELECT'),
                   has_table_privilege('gutcare_notification_worker','health.medication_plan','SELECT')
        """)
        ).one()
        assert privileges == (True, False, False, False, False)
        tables = (
            db.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid IN ('health.notification_preference'::regclass,'health.notification_outbox'::regclass,'health.patient_notification'::regclass) ORDER BY oid"
                )
            )
            .scalars()
            .all()
        )
        assert tables == [True, True, True]
    with _sessions(worker_engine).begin() as db:
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient)})
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text("""
                    INSERT INTO health.notification_outbox
                    (patient_id,event_type,target_type,target_id,occurred_at,priority,deduplication_key,payload)
                    SELECT patient_id,event_type,target_type,target_id,occurred_at,priority,
                           deduplication_key||chr(58)||'forged',payload
                    FROM health.notification_outbox WHERE patient_id=:p LIMIT 1
                """),
                    {"p": patient},
                )
    with _sessions(app_engine).begin() as db:
        db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        account = db.get(UserAccount, user)
        assert account is not None
        account.status = "deactivated"
    with pytest.raises(Problem) as frozen:
        notifications.list_notifications(context, 20, None, None, False)
    assert frozen.value.status == 401
    worker_engine.dispose()
