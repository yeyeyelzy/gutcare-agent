"""Grant the patient app the narrow read needed for deletion-job idempotency."""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_file_delete_conflict"
down_revision: str | None = "0029_f02_worker_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL requires SELECT on ON CONFLICT's target column, even for
    # DO NOTHING. Keep the grant column-scoped; the app still cannot read jobs.
    op.execute("GRANT SELECT (file_object_id) ON integration.file_deletion_job TO gutcare_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT (file_object_id) ON integration.file_deletion_job FROM gutcare_app")
