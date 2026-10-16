"""Persist conservative patient-confirmed laboratory result conflicts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_f02_lab_result_conflicts"
down_revision: str | None = "0021_f02_parse_outcome"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _secure(table: str) -> None:
    op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON health.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        f"CREATE POLICY {table}_privacy_worker ON health.{table} "
        "FOR ALL TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )


def upgrade() -> None:
    op.drop_constraint(
        "ck_medical_candidate_value_type",
        "medical_field_candidate",
        schema="health",
        type_="check",
    )
    op.create_check_constraint(
        "ck_medical_candidate_value_type",
        "medical_field_candidate",
        "value_type IN ('string','date','decimal','integer','boolean','diagnosis','object')",
        schema="health",
    )
    op.create_check_constraint(
        "ck_medical_candidate_field_type",
        "medical_field_candidate",
        "(field_code = 'diagnosis' AND value_type = 'diagnosis') OR "
        "(field_code = 'document_date' AND value_type = 'date') OR "
        "(field_code = 'weight_kg' AND value_type = 'decimal') OR "
        "(field_code IN ('recommendation','test_item','medication_name',"
        "'medication_frequency','medication_duration','allergy') AND value_type = 'string') OR "
        "(field_code IN ('test_result','medication_dose') AND value_type = 'object')",
        schema="health",
    )
    op.create_table(
        "medical_fact_conflict",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_hash", sa.CHAR(64), nullable=False),
        sa.Column("membership_fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolution", sa.String(24)),
        sa.Column("resolution_key", sa.String(128)),
        sa.Column("request_hash", sa.CHAR(64)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason_code", sa.String(32)),
        sa.Column("invalidated_source_version", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'invalidated')", name="ck_medical_fact_conflict_status"
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_medical_fact_conflict_version"),
        sa.CheckConstraint(
            "(status = 'open' AND resolution IS NULL AND resolution_key IS NULL "
            "AND request_hash IS NULL AND resolved_at IS NULL "
            "AND invalidation_reason_code IS NULL) "
            "OR (status = 'resolved' AND resolution = 'keep_both' AND resolution_key IS NOT NULL "
            "AND request_hash IS NOT NULL AND resolved_at IS NOT NULL "
            "AND invalidation_reason_code IS NULL) "
            "OR (status = 'invalidated' AND resolution IS NULL AND resolution_key IS NULL "
            "AND request_hash IS NULL AND invalidation_reason_code IN "
            "('source_deleted', 'source_changed') AND invalidated_source_version >= 1)",
            name="ck_medical_fact_conflict_state_shape",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "patient_id", name="uq_medical_fact_conflict_id_patient"),
        sa.UniqueConstraint(
            "patient_id", "membership_fingerprint", name="uq_medical_fact_conflict_fingerprint"
        ),
        sa.UniqueConstraint(
            "patient_id", "resolution_key", name="uq_medical_fact_conflict_resolution_key"
        ),
        schema="health",
    )
    op.create_index(
        "ix_medical_fact_conflict_patient_status",
        "medical_fact_conflict",
        ["patient_id", "status", "created_at"],
        schema="health",
    )
    op.create_table(
        "medical_fact_conflict_member",
        sa.Column("conflict_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_role", sa.String(16), nullable=False),
        sa.Column("fact_version", sa.Integer(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("sampled_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "member_role IN ('test_item', 'test_result')", name="ck_medical_conflict_member_role"
        ),
        sa.CheckConstraint(
            "fact_version >= 1 AND document_version >= 1",
            name="ck_medical_conflict_member_versions",
        ),
        sa.ForeignKeyConstraint(
            ["conflict_id", "patient_id"],
            ["health.medical_fact_conflict.id", "health.medical_fact_conflict.patient_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fact_id", "patient_id"],
            ["health.confirmed_medical_fact.id", "health.confirmed_medical_fact.patient_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "conflict_id", "patient_id", "fact_id", name="uq_medical_conflict_member_fact"
        ),
        sa.UniqueConstraint(
            "conflict_id",
            "patient_id",
            "document_id",
            "member_role",
            name="uq_medical_conflict_member_document_role",
        ),
        schema="health",
    )
    op.create_index(
        "ix_medical_conflict_member_patient_fact",
        "medical_fact_conflict_member",
        ["patient_id", "fact_id"],
        schema="health",
    )
    for table in ("medical_fact_conflict", "medical_fact_conflict_member"):
        _secure(table)
    op.execute("GRANT SELECT, INSERT ON health.medical_fact_conflict TO gutcare_app")
    op.execute(
        "GRANT UPDATE (status, record_version, resolution, resolution_key, request_hash, "
        "resolved_at, invalidation_reason_code, invalidated_source_version, updated_at) "
        "ON health.medical_fact_conflict TO gutcare_app"
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON health.medical_fact_conflict_member TO gutcare_app")
    op.execute(
        "GRANT SELECT, DELETE ON health.medical_fact_conflict, "
        "health.medical_fact_conflict_member TO gutcare_privacy_worker"
    )
    op.execute(
        "REVOKE ALL ON health.medical_fact_conflict, health.medical_fact_conflict_member "
        "FROM PUBLIC, gutcare_worker, gutcare_analysis_worker, gutcare_notification_worker"
    )


def downgrade() -> None:
    bind = op.get_bind()
    object_count = bind.scalar(
        sa.text("SELECT count(*) FROM health.medical_field_candidate WHERE value_type = 'object'")
    )
    invalid_pair_count = bind.scalar(
        sa.text(
            "SELECT count(*) FROM health.medical_field_candidate WHERE NOT ("
            "(field_code = 'diagnosis' AND value_type = 'diagnosis') OR "
            "(field_code = 'document_date' AND value_type = 'date') OR "
            "(field_code = 'weight_kg' AND value_type = 'decimal') OR "
            "(field_code IN ('recommendation','test_item','medication_name',"
            "'medication_frequency','medication_duration','allergy') AND value_type = 'string') OR "
            "(field_code IN ('test_result','medication_dose') AND value_type = 'object'))"
        )
    )
    if invalid_pair_count:
        raise RuntimeError("Refusing to downgrade with non-contract F02 candidate type pairs")
    if object_count:
        raise RuntimeError("Refusing to remove supported object-valued F02 candidate schema")
    count = bind.scalar(sa.text("SELECT count(*) FROM health.medical_fact_conflict"))
    if count:
        raise RuntimeError("Refusing to downgrade with persisted F02 conflict audit data")
    op.drop_constraint(
        "ck_medical_candidate_field_type",
        "medical_field_candidate",
        schema="health",
        type_="check",
    )
    op.drop_constraint(
        "ck_medical_candidate_value_type",
        "medical_field_candidate",
        schema="health",
        type_="check",
    )
    op.create_check_constraint(
        "ck_medical_candidate_value_type",
        "medical_field_candidate",
        "value_type IN ('string','date','decimal','integer','boolean','diagnosis')",
        schema="health",
    )
    op.drop_index(
        "ix_medical_conflict_member_patient_fact",
        table_name="medical_fact_conflict_member",
        schema="health",
    )
    op.drop_table("medical_fact_conflict_member", schema="health")
    op.drop_index(
        "ix_medical_fact_conflict_patient_status",
        table_name="medical_fact_conflict",
        schema="health",
    )
    op.drop_table("medical_fact_conflict", schema="health")
