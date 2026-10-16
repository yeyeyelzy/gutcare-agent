"""Add the independent F02 patient-decision idempotency ledger and task lock policy."""

import json
from collections.abc import Sequence
from hashlib import sha256
from uuid import uuid4

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0012_f02_decision_ledger"
down_revision: str | None = "0011_f02_medical_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medical_candidate_decision_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False, server_default="204"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("response_status = 204", name="ck_medical_decision_idempotency_status"),
        sa.ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_decision_idempotency_candidate_patient",
        ),
        sa.UniqueConstraint(
            "patient_id", "idempotency_key", name="uq_medical_decision_idempotency_key"
        ),
        schema="health",
    )
    if not context.is_offline_mode():
        connection = op.get_bind()
        connection.execute(
            sa.text("ALTER TABLE health.medical_candidate_decision DISABLE ROW LEVEL SECURITY")
        )
        historical = connection.execute(
            sa.text(
                "SELECT patient_id, candidate_id, idempotency_key, decision, chosen_value "
                "FROM health.medical_candidate_decision"
            )
        ).mappings()
        for row in historical:
            request_hash = sha256(
                json.dumps(
                    {
                        "action": row["decision"],
                        "corrected_value": row["chosen_value"]
                        if row["decision"] == "correct"
                        else None,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            connection.execute(
                sa.text(
                    "INSERT INTO health.medical_candidate_decision_idempotency "
                    "(id, patient_id, candidate_id, idempotency_key, "
                    "request_hash, response_status) "
                    "VALUES (:id, :patient_id, :candidate_id, :idempotency_key, :request_hash, 204)"
                ),
                {
                    "id": uuid4(),
                    "patient_id": row["patient_id"],
                    "candidate_id": row["candidate_id"],
                    "idempotency_key": row["idempotency_key"],
                    "request_hash": request_hash,
                },
            )
        connection.execute(
            sa.text("ALTER TABLE health.medical_candidate_decision ENABLE ROW LEVEL SECURITY")
        )
    op.execute(
        "ALTER TABLE health.medical_candidate_decision_idempotency ENABLE ROW LEVEL SECURITY"
    )
    op.execute("ALTER TABLE health.medical_candidate_decision_idempotency FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY medical_candidate_decision_idempotency_patient_isolation "
        "ON health.medical_candidate_decision_idempotency "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "GRANT SELECT, INSERT ON health.medical_candidate_decision_idempotency TO gutcare_app"
    )
    op.execute(
        "REVOKE ALL ON health.medical_candidate_decision_idempotency FROM PUBLIC, gutcare_worker"
    )
    op.execute("REVOKE UPDATE ON health.patient_profile FROM gutcare_worker")


def downgrade() -> None:
    op.execute("GRANT UPDATE ON health.patient_profile TO gutcare_worker")
    op.execute(
        "DROP POLICY medical_candidate_decision_idempotency_patient_isolation "
        "ON health.medical_candidate_decision_idempotency"
    )
    op.drop_table("medical_candidate_decision_idempotency", schema="health")
