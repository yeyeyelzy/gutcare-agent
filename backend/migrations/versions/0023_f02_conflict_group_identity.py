"""Use stable patient-scoped group identity for active A07 conflicts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_f02_conflict_group_identity"
down_revision: str | None = "0022_f02_lab_result_conflicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM health.medical_fact_conflict "
        "WHERE status <> 'invalidated' GROUP BY patient_id, group_hash HAVING count(*) > 1) "
        "THEN RAISE EXCEPTION 'duplicate active medical conflict groups prevent upgrade'; END IF; "
        "END $$"
    )
    op.drop_constraint(
        "uq_medical_fact_conflict_fingerprint", "medical_fact_conflict", schema="health"
    )
    op.create_index(
        "uq_medical_fact_conflict_patient_group_active",
        "medical_fact_conflict",
        ["patient_id", "group_hash"],
        unique=True,
        postgresql_where=sa.text("status <> 'invalidated'"),
        schema="health",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM health.medical_fact_conflict "
            "GROUP BY patient_id, membership_fingerprint HAVING count(*) > 1)"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade A07 group identity while duplicate membership fingerprints exist"
        )
    op.drop_index(
        "uq_medical_fact_conflict_patient_group_active",
        table_name="medical_fact_conflict",
        schema="health",
    )
    op.create_unique_constraint(
        "uq_medical_fact_conflict_fingerprint",
        "medical_fact_conflict",
        ["patient_id", "membership_fingerprint"],
        schema="health",
    )
