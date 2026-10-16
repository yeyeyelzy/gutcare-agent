"""Add auditable F05 symptom status and controlled symptom descriptions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_f05_symptom_status_history"
down_revision: str | None = "0007_f03_f05_records_risk_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "symptom_record",
        sa.Column("symptom_status", sa.String(16), nullable=False, server_default="ongoing"),
        schema="health",
    )
    op.create_check_constraint(
        "ck_symptom_record_status",
        "symptom_record",
        "symptom_status IN ('ongoing','relieved')",
        schema="health",
    )
    op.add_column("symptom_item", sa.Column("other_description", sa.String(160)), schema="health")
    op.create_check_constraint(
        "ck_symptom_code",
        "symptom_item",
        "symptom_code IN ('abdominal_pain','bloating','diarrhea','constipation','nausea',"
        "'vomiting','acid_reflux','appetite_change','blood_in_stool_concern','other')",
        schema="health",
    )
    op.create_check_constraint(
        "ck_symptom_other_description",
        "symptom_item",
        "(symptom_code = 'other' AND other_description IS NOT NULL "
        "AND length(btrim(other_description)) BETWEEN 1 AND 160) "
        "OR (symptom_code <> 'other' AND other_description IS NULL)",
        schema="health",
    )
    op.create_table(
        "symptom_status_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("symptom_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["symptom_record_id", "patient_id"],
            ["health.symptom_record.id", "health.symptom_record.patient_id"],
            ondelete="CASCADE",
            name="fk_symptom_status_event_record_patient",
        ),
        sa.CheckConstraint("status IN ('ongoing','relieved')", name="ck_symptom_status_event"),
        schema="health",
    )
    op.create_index(
        "ix_symptom_status_event_patient_record_time",
        "symptom_status_event",
        ["patient_id", "symptom_record_id", "changed_at"],
        schema="health",
    )
    op.execute("ALTER TABLE health.symptom_status_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.symptom_status_event FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY symptom_status_event_patient_isolation "
        "ON health.symptom_status_event "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute("REVOKE ALL ON health.symptom_status_event FROM gutcare_app")
    op.execute("GRANT SELECT, INSERT ON health.symptom_status_event TO gutcare_app")


def downgrade() -> None:
    op.drop_table("symptom_status_event", schema="health")
    op.drop_constraint("ck_symptom_other_description", "symptom_item", schema="health")
    op.drop_constraint("ck_symptom_code", "symptom_item", schema="health")
    op.drop_column("symptom_item", "other_description", schema="health")
    op.drop_constraint("ck_symptom_record_status", "symptom_record", schema="health")
    op.drop_column("symptom_record", "symptom_status", schema="health")
