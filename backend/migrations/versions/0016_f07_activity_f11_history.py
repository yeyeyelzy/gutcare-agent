"""Add F07 activity records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_f07_activity_f11_history"
down_revision: str | None = "0015_f12_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_type", sa.String(16), nullable=False),
        sa.Column("description", sa.String(160)),
        sa.Column("intensity", sa.String(16), nullable=False),
        sa.Column("subjective_feeling", sa.String(16), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "activity_type IN ('walking','jogging','cycling','other')", name="ck_activity_type"
        ),
        sa.CheckConstraint(
            "(activity_type = 'other' AND description IS NOT NULL AND "
            "length(btrim(description)) BETWEEN 1 AND 160) OR "
            "(activity_type <> 'other' AND description IS NULL)",
            name="ck_activity_other_description",
        ),
        sa.CheckConstraint("intensity IN ('low','moderate','high')", name="ck_activity_intensity"),
        sa.CheckConstraint(
            "subjective_feeling IN ('better','same','worse')", name="ck_activity_feeling"
        ),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="ck_activity_duration"),
        sa.CheckConstraint("record_version >= 1", name="ck_activity_record_version"),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="health",
    )
    op.create_index(
        "ix_activity_record_patient_occurred",
        "activity_record",
        ["patient_id", "occurred_at"],
        schema="health",
    )
    op.execute("ALTER TABLE health.activity_record ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.activity_record FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY activity_record_patient_isolation ON health.activity_record
        USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
        WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON health.activity_record TO gutcare_app")


def downgrade() -> None:
    op.drop_table("activity_record", schema="health")
