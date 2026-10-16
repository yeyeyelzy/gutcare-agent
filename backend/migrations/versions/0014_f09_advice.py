"""Add F09 advice, evidence and feedback lifecycle."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_f09_advice"
down_revision: str | None = "0013_f08_analysis_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _secure(table: str) -> None:
    op.execute(f"ALTER TABLE analysis.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE analysis.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON analysis.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "health_advice",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("uncertainty", postgresql.JSONB(), nullable=False),
        sa.Column("applicability", postgresql.JSONB(), nullable=False),
        sa.Column("safety_boundary", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("basis_updated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("basis_updated_at", sa.DateTime(timezone=True)),
        sa.Column("basis_update_reason", sa.String(32)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "category IN ('diet','lifestyle','record_management',"
            "'medication_adherence','care_consultation')",
            name="ck_advice_category",
        ),
        sa.CheckConstraint("priority IN ('routine','important')", name="ck_advice_priority"),
        sa.CheckConstraint("status IN ('new','read','archived')", name="ck_advice_status"),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 160 AND length(body) BETWEEN 1 AND 3000",
            name="ck_advice_text_lengths",
        ),
        sa.CheckConstraint(
            "(basis_updated = false AND basis_updated_at IS NULL AND basis_update_reason IS NULL) "
            "OR (basis_updated = true AND basis_updated_at IS NOT NULL AND "
            "basis_update_reason IN ('source_updated','source_deleted','fact_replaced'))",
            name="ck_advice_basis_update",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_health_advice_id_patient"),
        sa.ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        schema="analysis",
    )
    op.create_index(
        "ix_health_advice_patient_created",
        "health_advice",
        ["patient_id", "created_at"],
        schema="analysis",
    )
    op.create_table(
        "advice_evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("advice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(40)),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_version", sa.Integer()),
        sa.Column("locator", sa.String(160)),
        sa.Column("source_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("knowledge_ref", sa.String(160)),
        sa.Column("knowledge_version", sa.String(64)),
        sa.Column("knowledge_title", sa.String(240)),
        sa.Column("knowledge_publisher", sa.String(160)),
        sa.Column("citation_url", sa.String(2048)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(evidence_type='patient' AND source_type IS NOT NULL AND source_id IS NOT NULL "
            "AND source_version >= 1 AND "
            "((source_deleted = false AND locator IS NOT NULL) OR "
            "(source_deleted = true AND locator IS NULL)) AND knowledge_ref IS NULL "
            "AND knowledge_version IS NULL AND knowledge_title IS NULL "
            "AND knowledge_publisher IS NULL AND citation_url IS NULL) OR "
            "(evidence_type='knowledge' AND source_type IS NULL AND source_id IS NULL "
            "AND source_version IS NULL AND locator IS NULL AND knowledge_ref IS NOT NULL "
            "AND knowledge_version IS NOT NULL AND knowledge_title IS NOT NULL "
            "AND knowledge_publisher IS NOT NULL AND source_deleted = false)",
            name="ck_advice_evidence_shape",
        ),
        sa.ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        schema="analysis",
    )
    op.create_table(
        "advice_callback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("task_id", "callback_id", name="uq_advice_callback_task_id"),
        schema="analysis",
    )
    op.create_table(
        "advice_feedback",
        sa.Column("advice_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("feedback_type", sa.String(24), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "feedback_type IN ('helpful','not_helpful','not_applicable')",
            name="ck_advice_feedback_type",
        ),
        sa.ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        schema="analysis",
    )
    op.create_table(
        "advice_feedback_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("advice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("feedback_type", sa.String(24), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "feedback_type IN ('helpful','not_helpful','not_applicable')",
            name="ck_advice_feedback_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("patient_id", "idempotency_key", name="uq_advice_feedback_event_key"),
        schema="analysis",
    )
    tables = (
        "health_advice",
        "advice_evidence",
        "advice_callback",
        "advice_feedback",
        "advice_feedback_event",
    )
    for table in tables:
        _secure(table)
    for table in ("health_advice", "advice_evidence", "advice_callback"):
        op.execute(
            f"CREATE POLICY {table}_analysis_worker ON analysis.{table} "
            "FOR ALL TO gutcare_analysis_worker "
            "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
            "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE ON analysis.health_advice TO gutcare_app")
    op.execute("GRANT SELECT, INSERT ON analysis.advice_evidence TO gutcare_app")
    op.execute("GRANT UPDATE (locator, source_deleted) ON analysis.advice_evidence TO gutcare_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON analysis.advice_feedback TO gutcare_app")
    op.execute("GRANT SELECT, INSERT ON analysis.advice_feedback_event TO gutcare_app")
    op.execute(
        "GRANT SELECT, INSERT ON analysis.health_advice, analysis.advice_evidence, "
        "analysis.advice_callback TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analysis "
        "TO gutcare_app, gutcare_analysis_worker"
    )
    op.execute(
        "REVOKE ALL ON analysis.health_advice, analysis.advice_evidence, "
        "analysis.advice_callback, analysis.advice_feedback, "
        "analysis.advice_feedback_event FROM PUBLIC"
    )


def downgrade() -> None:
    for table in (
        "advice_feedback_event",
        "advice_feedback",
        "advice_callback",
        "advice_evidence",
        "health_advice",
    ):
        op.drop_table(table, schema="analysis")
