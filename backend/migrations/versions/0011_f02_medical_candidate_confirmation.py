"""Persist F02 parse requests, typed candidates, patient decisions and facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_f02_medical_candidates"
down_revision: str | None = "0010_f06_source_refs"
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
    op.create_table(
        "medical_parse_request",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("callback_id", postgresql.UUID(as_uuid=True)),
        sa.Column("callback_hash", sa.CHAR(64)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','processing','needs_confirmation','succeeded','failed',"
            "'cancelled','invalidated')",
            name="ck_medical_parse_request_status",
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_medical_parse_request_version"),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_parse_request_document_patient",
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_parse_request_file_patient",
        ),
        sa.UniqueConstraint(
            "document_id", "record_version", name="uq_medical_parse_request_document_version"
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_medical_parse_request_id_patient"),
        sa.UniqueConstraint("id", "callback_id", name="uq_medical_parse_request_callback"),
        schema="health",
    )
    op.create_index(
        "ix_medical_parse_request_claim",
        "medical_parse_request",
        ["status", "created_at"],
        schema="health",
    )
    op.create_table(
        "medical_field_candidate",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_code", sa.String(48), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("confidence", sa.Float()),
        sa.Column("uncertainty", sa.String(500)),
        sa.Column("source_locator", postgresql.JSONB()),
        sa.Column("excerpt", sa.String(500)),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "value_type IN ('string','date','decimal','integer','boolean','diagnosis')",
            name="ck_medical_candidate_value_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','accepted','corrected','rejected','invalidated')",
            name="ck_medical_field_candidate_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_medical_field_candidate_confidence",
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_medical_candidate_version"),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            ["health.medical_parse_request.id", "health.medical_parse_request.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_candidate_request_patient",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_medical_candidate_id_patient"),
        schema="health",
    )
    op.create_index(
        "ix_medical_candidate_patient_request",
        "medical_field_candidate",
        ["patient_id", "request_id", "review_status"],
        schema="health",
    )
    op.create_table(
        "confirmed_medical_fact",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_code", sa.String(48), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("fact_status", sa.String(24), nullable=False, server_default="active"),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "fact_status IN ('active','rejected','superseded','source_deleted')",
            name="ck_confirmed_medical_fact_status",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="RESTRICT",
            name="fk_confirmed_fact_candidate_patient",
        ),
        sa.UniqueConstraint("candidate_id", name="uq_confirmed_fact_candidate"),
        sa.UniqueConstraint("id", "patient_id", name="uq_confirmed_fact_id_patient"),
        schema="health",
    )
    op.create_table(
        "medical_candidate_decision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("chosen_value", postgresql.JSONB()),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "decision IN ('accept','correct','reject')", name="ck_medical_candidate_decision"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_candidate_decision_patient",
        ),
        sa.UniqueConstraint(
            "patient_id", "idempotency_key", name="uq_medical_candidate_decision_idempotency"
        ),
        schema="health",
    )
    for table in (
        "medical_parse_request",
        "medical_field_candidate",
        "confirmed_medical_fact",
        "medical_candidate_decision",
    ):
        _rls(table)
    op.execute(
        "CREATE POLICY medical_parse_request_agent_task ON health.medical_parse_request "
        "USING (id = NULLIF(current_setting('app.medical_parse_request_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY medical_parse_request_worker ON health.medical_parse_request "
        "FOR ALL TO gutcare_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON health.medical_parse_request, "
        "health.medical_field_candidate TO gutcare_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON health.confirmed_medical_fact, "
        "health.medical_candidate_decision TO gutcare_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON health.medical_parse_request, "
        "health.medical_field_candidate TO gutcare_worker"
    )
    op.execute(
        "GRANT SELECT ON health.confirmed_medical_fact, "
        "health.medical_candidate_decision TO gutcare_worker"
    )
    op.execute("REVOKE ALL ON health.confirmed_medical_fact FROM PUBLIC, gutcare_worker")
    op.execute("REVOKE ALL ON health.medical_candidate_decision FROM PUBLIC, gutcare_worker")


def downgrade() -> None:
    for table in (
        "medical_candidate_decision",
        "confirmed_medical_fact",
        "medical_field_candidate",
        "medical_parse_request",
    ):
        if table == "medical_parse_request":
            op.execute("DROP POLICY medical_parse_request_worker ON health.medical_parse_request")
            op.execute(
                "DROP POLICY medical_parse_request_agent_task ON health.medical_parse_request"
            )
        op.execute(f"DROP POLICY {table}_patient_isolation ON health.{table}")
        op.drop_table(table, schema="health")
