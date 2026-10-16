"""Add F08 patient-scoped analysis tasks and immutable snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_f08_analysis_tasks"
down_revision: str | None = "0012_f02_decision_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analysis")
    op.execute(
        "GRANT USAGE ON SCHEMA analysis TO gutcare_app, gutcare_worker, gutcare_analysis_worker"
    )
    op.create_table(
        "analysis_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("requested_from", sa.DateTime(timezone=True)),
        sa.Column("requested_to", sa.DateTime(timezone=True)),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("retry_of", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("result_payload", postgresql.JSONB()),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "analysis_type IN ('comprehensive_health_analysis','periodic_summary')",
            name="ck_analysis_task_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','partial','needs_input',"
            "'failed','cancelled')",
            name="ck_analysis_task_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_analysis_task_attempt"),
        sa.CheckConstraint(
            "requested_to IS NULL OR requested_from IS NULL OR requested_from < requested_to",
            name="ck_analysis_task_range",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_analysis_task_id_patient"),
        sa.UniqueConstraint("retry_of", "patient_id", name="uq_analysis_task_retry_once"),
        sa.ForeignKeyConstraint(
            ["retry_of", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="SET NULL (retry_of)",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="analysis",
    )
    op.create_index(
        "ix_analysis_task_patient_created",
        "analysis_task",
        ["patient_id", "created_at"],
        schema="analysis",
    )
    op.create_table(
        "task_input_snapshot",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        schema="analysis",
    )
    op.create_table(
        "analysis_task_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False, server_default="202"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("response_status = 202", name="ck_analysis_idempotency_status"),
        sa.ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "patient_id", "route", "idempotency_key", name="uq_analysis_idempotency_scope"
        ),
        schema="analysis",
    )
    op.create_table(
        "analysis_task_callback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callback_type", sa.String(16), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False, server_default="204"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("callback_type IN ('result','fail')", name="ck_analysis_callback_type"),
        sa.CheckConstraint("response_status = 204", name="ck_analysis_callback_status"),
        sa.ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("task_id", "callback_id", name="uq_analysis_task_callback"),
        schema="analysis",
    )
    for table in (
        "analysis_task",
        "task_input_snapshot",
        "analysis_task_idempotency",
        "analysis_task_callback",
    ):
        op.execute(f"ALTER TABLE analysis.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE analysis.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_patient_isolation ON analysis.{table} "
            "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
            "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
    for table in ("analysis_task", "task_input_snapshot", "analysis_task_callback"):
        op.execute(
            f"CREATE POLICY {table}_worker_access ON analysis.{table} "
            "FOR ALL TO gutcare_analysis_worker USING (true) WITH CHECK (true)"
        )
    op.execute(
        "CREATE FUNCTION analysis.reject_snapshot_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'task snapshots are immutable'; END $$"
    )
    op.execute(
        "CREATE TRIGGER task_input_snapshot_immutable BEFORE UPDATE "
        "ON analysis.task_input_snapshot FOR EACH ROW "
        "EXECUTE FUNCTION analysis.reject_snapshot_mutation()"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON analysis.analysis_task TO gutcare_app")
    op.execute(
        "GRANT SELECT, INSERT ON analysis.task_input_snapshot, "
        "analysis.analysis_task_idempotency TO gutcare_app"
    )
    op.execute("GRANT SELECT, UPDATE ON analysis.analysis_task TO gutcare_analysis_worker")
    op.execute("GRANT SELECT ON analysis.task_input_snapshot TO gutcare_analysis_worker")
    op.execute("GRANT SELECT, INSERT ON analysis.analysis_task_callback TO gutcare_analysis_worker")
    op.execute("GRANT USAGE ON SCHEMA health TO gutcare_analysis_worker")
    op.execute("GRANT SELECT ON health.patient_consent TO gutcare_analysis_worker")
    op.execute(
        "CREATE POLICY patient_consent_analysis_worker ON health.patient_consent "
        "FOR SELECT TO gutcare_analysis_worker USING (patient_id = "
        "NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "REVOKE ALL ON analysis.analysis_task, analysis.task_input_snapshot, "
        "analysis.analysis_task_idempotency, analysis.analysis_task_callback FROM PUBLIC"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_consent_analysis_worker ON health.patient_consent")
    op.execute("DROP TRIGGER task_input_snapshot_immutable ON analysis.task_input_snapshot")
    op.execute("DROP FUNCTION analysis.reject_snapshot_mutation()")
    op.drop_table("analysis_task_callback", schema="analysis")
    op.drop_table("analysis_task_idempotency", schema="analysis")
    op.drop_table("task_input_snapshot", schema="analysis")
    op.drop_index("ix_analysis_task_patient_created", table_name="analysis_task", schema="analysis")
    op.drop_table("analysis_task", schema="analysis")
