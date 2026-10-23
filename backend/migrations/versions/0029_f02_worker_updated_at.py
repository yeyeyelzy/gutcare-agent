"""Permit F02 claim worker to advance medical document update timestamp."""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_f02_worker_updated_at"
down_revision: str | None = "0028_f02_analysis_worker_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("GRANT UPDATE (updated_at) ON health.medical_document TO gutcare_analysis_worker")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (updated_at) ON health.medical_document FROM gutcare_analysis_worker")
