"""Create F03-F05 record tables and deterministic risk alerts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_f03_f05_records_risk_alerts"
down_revision: str | None = "0006_f02_file_worker_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _patient_rls(table: str) -> None:
    op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON health.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS safety")
    op.execute("GRANT USAGE ON SCHEMA safety TO gutcare_app, gutcare_worker")
    op.create_table(
        "diet_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.patient_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meal_type", sa.String(24)),
        sa.Column("text_description", sa.Text()),
        sa.Column("portion_note", sa.String(160)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="patient_manual"),
        sa.Column("confirmation_status", sa.String(24), nullable=False, server_default="confirmed"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "patient_id", name="uq_diet_record_id_patient"),
        sa.ForeignKeyConstraint(
            ["image_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
        ),
        schema="health",
    )
    op.create_index(
        "ix_diet_record_patient_occurred",
        "diet_record",
        ["patient_id", "occurred_at"],
        schema="health",
    )
    op.create_table(
        "diet_item",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("diet_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category_code", sa.String(64)),
        sa.Column("amount_text", sa.String(160)),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="patient_manual"),
        sa.Column("confirmed_by_patient", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["diet_record_id", "patient_id"],
            ["health.diet_record.id", "health.diet_record.patient_id"],
            ondelete="CASCADE",
        ),
        schema="health",
    )
    op.create_table(
        "stool_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.patient_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bristol_type", sa.SmallInteger()),
        sa.Column("color_code", sa.String(32)),
        sa.Column("blood_reported", sa.Boolean()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="patient_manual"),
        sa.Column("confirmation_status", sa.String(24), nullable=False, server_default="confirmed"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "bristol_type IS NULL OR bristol_type BETWEEN 1 AND 7", name="ck_stool_bristol"
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_stool_record_id_patient"),
        sa.ForeignKeyConstraint(
            ["image_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
        ),
        schema="health",
    )
    op.create_index(
        "ix_stool_record_patient_occurred",
        "stool_record",
        ["patient_id", "occurred_at"],
        schema="health",
    )
    op.create_table(
        "symptom_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.patient_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="patient_manual"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "patient_id", name="uq_symptom_record_id_patient"),
        schema="health",
    )
    op.create_index(
        "ix_symptom_record_patient_occurred",
        "symptom_record",
        ["patient_id", "occurred_at"],
        schema="health",
    )
    op.create_table(
        "symptom_item",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("symptom_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symptom_code", sa.String(48), nullable=False),
        sa.Column("severity", sa.SmallInteger()),
        sa.Column("body_location", sa.String(64)),
        sa.Column("patient_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["symptom_record_id", "patient_id"],
            ["health.symptom_record.id", "health.symptom_record.patient_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity BETWEEN 0 AND 10", name="ck_symptom_severity"
        ),
        schema="health",
    )
    op.create_table(
        "record_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.patient_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "patient_id", "operation", "idempotency_key", name="uq_record_idempotency_scope"
        ),
        schema="health",
    )
    op.create_table(
        "risk_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("condition_json", postgresql.JSONB(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(24), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False, server_default="test_only"),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("source_refs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("rule_code", "version", name="uq_risk_rule_code_version"),
        sa.CheckConstraint(
            "severity IN ('attention','seek_care','emergency')", name="ck_risk_rule_severity"
        ),
        sa.CheckConstraint(
            "review_status IN ('draft','approved','retired')", name="ck_risk_rule_review_status"
        ),
        sa.CheckConstraint(
            "environment IN ('production','test_only')", name="ck_risk_rule_environment"
        ),
        sa.CheckConstraint(
            "environment <> 'production' OR (review_status = 'approved' "
            "AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND jsonb_array_length(source_refs) > 0 AND expires_at IS NOT NULL)",
            name="ck_risk_rule_production_reviewed",
        ),
        schema="safety",
    )
    op.create_table(
        "risk_alert",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.patient_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.risk_rule.id"),
            nullable=False,
        ),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_version", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("deduplication_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="unread"),
        sa.Column(
            "triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("reevaluated_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_summary", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("patient_id", "deduplication_key", name="uq_risk_alert_patient_dedup"),
        sa.UniqueConstraint("id", "patient_id", name="uq_risk_alert_id_patient"),
        sa.CheckConstraint(
            "status IN ('unread','read','reevaluated')", name="ck_risk_alert_status"
        ),
        schema="safety",
    )
    op.create_table(
        "alert_evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("field_summary", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["alert_id", "patient_id"],
            ["safety.risk_alert.id", "safety.risk_alert.patient_id"],
            ondelete="CASCADE",
        ),
        schema="safety",
    )
    op.create_index(
        "ix_risk_alert_patient_status_time",
        "risk_alert",
        ["patient_id", "status", "triggered_at"],
        schema="safety",
    )
    op.execute("ALTER TABLE safety.risk_alert ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE safety.risk_alert FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY risk_alert_patient_isolation ON safety.risk_alert "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute("ALTER TABLE safety.alert_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE safety.alert_evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY alert_evidence_patient_isolation ON safety.alert_evidence "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    for table in (
        "diet_record",
        "diet_item",
        "stool_record",
        "symptom_record",
        "symptom_item",
        "record_idempotency",
    ):
        _patient_rls(table)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON health.diet_record, health.diet_item, "
        "health.stool_record, health.symptom_record, health.symptom_item, "
        "health.record_idempotency TO gutcare_app"
    )
    op.execute("GRANT SELECT ON safety.risk_rule TO gutcare_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON safety.risk_alert TO gutcare_app")
    op.execute("GRANT SELECT, INSERT ON safety.alert_evidence TO gutcare_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA health, safety TO gutcare_app")


def downgrade() -> None:
    op.drop_table("alert_evidence", schema="safety")
    op.drop_table("risk_alert", schema="safety")
    op.drop_table("risk_rule", schema="safety")
    for table in (
        "symptom_item",
        "symptom_record",
        "stool_record",
        "diet_item",
        "diet_record",
        "record_idempotency",
    ):
        op.drop_table(table, schema="health")
