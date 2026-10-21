"""FastAPI application factory and health endpoints."""

from collections.abc import Callable, Iterable  # noqa: I001 - preload logging before FastAPI on Python 3.13
import base64
import hmac
from dataclasses import dataclass
from pathlib import Path

from gutcare.shared.logging import configure_logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic.script import ScriptDirectory

from gutcare.auth.api import router as auth_router
from gutcare.auth.service import AuthService, RedisRateLimiter
from gutcare.files.api import agent_router, gateway_router, router as files_router
from gutcare.files.scanner import ClamAvScanner
from gutcare.files.service import FileService
from gutcare.files.storage import S3ObjectStorage
from gutcare.records.api import risk_router, router as records_router
from gutcare.records.image_api import router as record_image_router
from gutcare.records.image_worker import (
    RecordImageWorkerService,
    worker_router as record_image_worker_router,
)
from gutcare.records.service import RecordService
from gutcare.medication.api import router as medication_router
from gutcare.medication.service import MedicationService
from gutcare.analysis.api import agent_router as analysis_agent_router, router as analysis_router
from gutcare.analysis.service import AnalysisService
from gutcare.notifications.api import router as notifications_router
from gutcare.notifications.service import NotificationService
from gutcare.activity.api import router as activity_router
from gutcare.activity.service import ActivityService
from gutcare.mood.api import router as mood_router
from gutcare.mood.service import MoodService
from gutcare.privacy.api import router as privacy_router
from gutcare.privacy.service import PrivacyService
from gutcare.analysis.advice import (
    AdviceService,
    agent_router as advice_agent_router,
    router as advice_router,
)
from gutcare.config import Settings, get_settings
from gutcare.shared.errors import install_exception_handlers
from gutcare.shared.middleware import RequestIdMiddleware
from gutcare.shared.metrics import OperationsMetrics


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    available: bool
    schema_current: bool
    privacy_replay_clear: bool = True


DatabaseProbe = Callable[[], DatabaseReadiness]


def _health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/health/ready", include_in_schema=False, response_model=None)
    def ready(request: Request) -> JSONResponse | dict[str, str]:
        # Both connectivity and the expected Alembic revision are required for readiness.
        probe: DatabaseProbe | None = request.app.state.database_probe
        if not request.app.state.settings.database_url or probe is None:
            request.app.state.metrics.observe_readiness(
                "not_ready", database=False, schema=False, privacy_replay=False
            )
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        try:
            database = probe()
            ready = database.available and database.schema_current and database.privacy_replay_clear
        except Exception:
            request.app.state.metrics.observe_readiness(
                "not_ready", database=False, schema=False, privacy_replay=False
            )
            ready = False
        else:
            request.app.state.metrics.observe_readiness(
                "ready" if ready else "not_ready",
                database=database.available,
                schema=database.schema_current,
                privacy_replay=database.privacy_replay_clear,
            )
        if not ready:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ready"}

    return router


def _operations_router() -> APIRouter:
    router = APIRouter()

    @router.get("/ops/metrics", include_in_schema=False)
    def metrics(request: Request) -> Response:
        settings: Settings = request.app.state.settings
        token = settings.metrics_token
        if (
            not settings.metrics_enabled
            or not token
            or not hmac.compare_digest(request.headers.get("X-Ops-Metrics-Token", ""), token)
        ):
            return Response(status_code=404)

        engine = request.app.state.database_engine
        if engine is not None:
            try:
                with engine.connect() as connection:
                    rows = connection.execute(
                        text(
                            "SELECT queue, state, item_count, oldest_age_seconds "
                            "FROM public.gutcare_metrics_snapshot()"
                        )
                    ).all()
                request.app.state.metrics.update_backlog(
                    (str(queue), str(state), int(count), float(age))
                    for queue, state, count, age in rows
                )
            except Exception:
                # Scrapes must not serialize database exception text or arguments.
                request.app.state.metrics.mark_snapshot_failed()
        else:
            request.app.state.metrics.mark_snapshot_failed()
        return Response(
            content=generate_latest(request.app.state.metrics.registry),
            media_type=CONTENT_TYPE_LATEST,
            headers={"Cache-Control": "no-store"},
        )

    return router


def create_app(
    settings: Settings | None = None,
    database_probe: DatabaseProbe | None = None,
    routers: Iterable[APIRouter] = (),
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    application = FastAPI(
        title="GutCare Business API",
        version="1.0.0",
        docs_url=None if resolved_settings.env == "production" else "/docs",
        redoc_url=None,
    )
    application.state.settings = resolved_settings
    application.state.metrics = OperationsMetrics()
    application.state.database_probe = database_probe
    application.state.auth_service = None
    application.state.file_service = None
    application.state.record_service = None
    application.state.medication_service = None
    application.state.analysis_service = None
    application.state.analysis_worker_service = None
    application.state.record_image_worker_service = None
    application.state.advice_service = None
    application.state.advice_worker_service = None
    application.state.notification_service = None
    application.state.activity_service = None
    application.state.mood_service = None
    application.state.privacy_service = None
    application.state.database_engine = None
    privacy_storage = None
    analysis_worker_sessions = None
    if resolved_settings.database_url is not None:
        database_url = str(resolved_settings.database_url)
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_engine(database_url, pool_pre_ping=True)
        application.state.database_engine = engine
        if database_probe is None:
            alembic_config = Path(__file__).resolve().parents[2] / "alembic.ini"
            config = Config(str(alembic_config))
            migration_path = str(alembic_config.parent / "migrations").replace("%", "%%")
            config.set_main_option("script_location", migration_path)
            expected_heads = frozenset(ScriptDirectory.from_config(config).get_heads())

            def production_database_probe() -> DatabaseReadiness:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                    revisions = frozenset(
                        connection.scalars(text("SELECT version_num FROM alembic_version"))
                    )
                    replay_clear = bool(connection.scalar(text("SELECT privacy.replay_ready()")))
                return DatabaseReadiness(
                    available=True,
                    schema_current=revisions == expected_heads,
                    privacy_replay_clear=replay_clear,
                )

            application.state.database_probe = production_database_probe
        sessions = sessionmaker(engine, expire_on_commit=False)
        application.state.record_service = RecordService(
            sessions,
            allow_test_only_rules=(
                resolved_settings.risk_test_only_rules_enabled
                and resolved_settings.env in {"local", "test"}
            ),
        )
        application.state.medication_service = MedicationService(sessions)
        application.state.analysis_service = AnalysisService(
            sessions, resolved_settings.jwt_signing_key
        )
        application.state.advice_service = AdviceService(sessions)
        application.state.notification_service = NotificationService(sessions)
        application.state.activity_service = ActivityService(
            sessions, resolved_settings.jwt_signing_key
        )
        application.state.mood_service = MoodService(
            sessions, resolved_settings.mood_idempotency_hmac_key
        )
        if resolved_settings.email_lookup_pepper:
            privacy_key = None
            if resolved_settings.export_kek:
                padded_key = resolved_settings.export_kek + "=" * (
                    -len(resolved_settings.export_kek) % 4
                )
                decoded_key = base64.urlsafe_b64decode(padded_key.encode())
                if len(decoded_key) == 32:
                    privacy_key = decoded_key
            if (
                resolved_settings.object_storage_endpoint is not None
                and resolved_settings.object_storage_access_key
                and resolved_settings.object_storage_secret_key
            ):
                privacy_storage = S3ObjectStorage(
                    str(resolved_settings.object_storage_endpoint),
                    resolved_settings.object_storage_access_key,
                    resolved_settings.object_storage_secret_key,
                )
            application.state.privacy_service = PrivacyService(
                sessions,
                resolved_settings.email_lookup_pepper,
                privacy_storage,
                privacy_key,
                resolved_settings.object_storage_bucket,
            )
        if resolved_settings.analysis_worker_database_url is not None:
            worker_database_url = str(resolved_settings.analysis_worker_database_url)
            if worker_database_url.startswith("postgresql://"):
                worker_database_url = worker_database_url.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
            worker_engine = create_engine(worker_database_url, pool_pre_ping=True)
            analysis_worker_sessions = sessionmaker(worker_engine, expire_on_commit=False)
            application.state.analysis_worker_service = AnalysisService(
                analysis_worker_sessions, resolved_settings.jwt_signing_key
            )
            application.state.advice_worker_service = AdviceService(analysis_worker_sessions)
        rate_limiter = None
        if resolved_settings.redis_url:
            rate_limiter = RedisRateLimiter(Redis.from_url(resolved_settings.redis_url))
        application.state.auth_service = AuthService(
            resolved_settings, sessions, rate_limiter=rate_limiter
        )
        if (
            resolved_settings.object_storage_endpoint is not None
            and resolved_settings.object_storage_access_key
            and resolved_settings.object_storage_secret_key
            and resolved_settings.clamav_host
            and resolved_settings.files_capability_secret
        ):
            storage = privacy_storage or S3ObjectStorage(
                str(resolved_settings.object_storage_endpoint),
                resolved_settings.object_storage_access_key,
                resolved_settings.object_storage_secret_key,
            )
            application.state.file_service = FileService(
                sessions,
                storage,
                ClamAvScanner(
                    resolved_settings.clamav_host,
                    resolved_settings.clamav_port,
                    resolved_settings.clamav_timeout_seconds,
                ),
                str(resolved_settings.public_base_url),
                resolved_settings.object_storage_bucket,
                resolved_settings.files_capability_secret,
            )
    if analysis_worker_sessions is not None and application.state.file_service is not None:
        application.state.record_image_worker_service = RecordImageWorkerService(
            analysis_worker_sessions, application.state.file_service._storage
        )
    application.add_middleware(
        RequestIdMiddleware,
        service_name=resolved_settings.service_name,
        metrics=application.state.metrics,
    )
    install_exception_handlers(application)
    application.include_router(_health_router())
    application.include_router(_operations_router())
    application.include_router(auth_router)
    application.include_router(files_router)
    application.include_router(mood_router)
    application.include_router(agent_router)
    application.include_router(gateway_router)
    application.include_router(risk_router)
    application.include_router(record_image_router)
    application.include_router(medication_router)
    application.include_router(analysis_router)
    application.include_router(analysis_agent_router)
    application.include_router(record_image_worker_router)
    application.include_router(advice_router)
    application.include_router(advice_agent_router)
    application.include_router(notifications_router)
    application.include_router(activity_router)
    application.include_router(privacy_router)
    for router in routers:
        application.include_router(router)
    # This router uses catch-all /{record_type} patterns; it must follow every
    # concrete built-in and extension router so it cannot shadow their routes.
    application.include_router(records_router)
    application.state.metrics.set_route_templates(
        route.path for route in application.routes if isinstance(route, APIRoute)
    )
    return application
