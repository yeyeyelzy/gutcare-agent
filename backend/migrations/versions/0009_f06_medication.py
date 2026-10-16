"""Create F06 medication plans, schedules, checkins, and idempotency ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_f06_medication"
down_revision: str | None = "0008_f05_symptom_status_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON health.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_medical_document_id_patient", "medical_document", ["id", "patient_id"], schema="health"
    )
    op.create_table(
        "medication_plan",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("medication_name", sa.String(160), nullable=False),
        sa.Column("dosage_text", sa.String(160)),
        sa.Column("route_code", sa.String(32)),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmation_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("plan_status", sa.String(24), nullable=False, server_default="discontinued"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "source_type IN ('manual','medical_document')", name="ck_med_plan_source"
        ),
        sa.CheckConstraint(
            "confirmation_status IN ('pending','confirmed','needs_review')",
            name="ck_med_plan_confirmation",
        ),
        sa.CheckConstraint(
            "plan_status IN ('active','ended','discontinued')", name="ck_med_plan_status"
        ),
        sa.CheckConstraint(
            "plan_status <> 'active' OR confirmation_status = 'confirmed'",
            name="ck_med_plan_activation",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_med_plan_dates",
        ),
        sa.CheckConstraint(
            "(source_type = 'manual' AND source_document_id IS NULL) OR "
            "(source_type = 'medical_document' AND source_document_id IS NOT NULL)",
            name="ck_med_plan_source_document",
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_med_plan_version"),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "patient_id", name="uq_med_plan_id_patient"),
        sa.ForeignKeyConstraint(
            ["source_document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            name="fk_med_plan_document_patient",
        ),
        schema="health",
    )
    op.create_index(
        "ix_med_plan_patient_status",
        "medication_plan",
        ["patient_id", "plan_status"],
        schema="health",
    )
    op.create_table(
        "medication_schedule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("rrule", sa.Text()),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_med_schedule_dates"
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_med_schedule_version"),
        sa.ForeignKeyConstraint(
            ["plan_id", "patient_id"],
            ["health.medication_plan.id", "health.medication_plan.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_med_schedule_id_patient"),
        schema="health",
    )
    op.create_index(
        "ix_med_schedule_patient_plan",
        "medication_schedule",
        ["patient_id", "plan_id"],
        schema="health",
    )
    op.create_table(
        "medication_checkin",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("taken_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('taken','not_taken','pending','skipped')", name="ck_med_checkin_status"
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_med_checkin_version"),
        sa.CheckConstraint(
            "(status = 'taken' AND taken_at IS NOT NULL) OR "
            "(status <> 'taken' AND taken_at IS NULL)",
            name="ck_med_checkin_taken_at",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id", "patient_id"],
            ["health.medication_schedule.id", "health.medication_schedule.patient_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("schedule_id", "local_date", name="uq_med_checkin_schedule_local_date"),
        sa.UniqueConstraint("id", "patient_id", name="uq_med_checkin_id_patient"),
        schema="health",
    )
    op.create_index(
        "ix_med_checkin_patient_scheduled",
        "medication_checkin",
        ["patient_id", "scheduled_for"],
        schema="health",
    )
    op.create_table(
        "medication_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "patient_id", "route", "idempotency_key", name="uq_med_idempotency_scope"
        ),
        schema="health",
    )
    for table in (
        "medication_plan",
        "medication_schedule",
        "medication_checkin",
        "medication_idempotency",
    ):
        _rls(table)
    op.execute(
        "CREATE POLICY medication_plan_worker_read ON health.medication_plan "
        "FOR SELECT TO gutcare_worker USING "
        "(deleted_at IS NULL AND confirmation_status = 'confirmed' AND plan_status = 'active')"
    )
    op.execute(
        "CREATE POLICY medication_schedule_worker_read ON health.medication_schedule "
        "FOR SELECT TO gutcare_worker USING (enabled AND deleted_at IS NULL)"
    )
    op.execute(
        "CREATE POLICY medication_checkin_worker_insert ON health.medication_checkin "
        "FOR INSERT TO gutcare_worker WITH CHECK (true)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON health.medication_plan, "
        "health.medication_schedule TO gutcare_app"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON health.medication_checkin TO gutcare_app")
    op.execute("GRANT SELECT, INSERT ON health.medication_idempotency TO gutcare_app")
    op.execute(
        "GRANT SELECT ON health.medication_plan, health.medication_schedule TO gutcare_worker"
    )
    op.execute("GRANT INSERT ON health.medication_checkin TO gutcare_worker")


def downgrade() -> None:
    for table in (
        "medication_idempotency",
        "medication_checkin",
        "medication_schedule",
        "medication_plan",
    ):
        op.execute(f"DROP POLICY {table}_patient_isolation ON health.{table}")
    op.drop_table("medication_idempotency", schema="health")
    op.drop_table("medication_checkin", schema="health")
    op.drop_table("medication_schedule", schema="health")
    op.drop_table("medication_plan", schema="health")
    op.drop_constraint("uq_medical_document_id_patient", "medical_document", schema="health")
