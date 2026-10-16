"""Enforce patient-scoped RLS on the file deletion queue."""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_nfr_file_deletion_job_rls"
down_revision: str | None = "0018_readiness_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The generic file worker has no authentication/account responsibility;
    # remove historical broad default grants on identity-bearing tables.
    op.execute(
        "REVOKE ALL ON iam.user_account, iam.refresh_session, "
        "iam.email_verification_token FROM gutcare_worker, gutcare_analysis_worker, "
        "gutcare_notification_worker"
    )
    op.execute("ALTER TABLE integration.file_deletion_job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration.file_deletion_job FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY file_deletion_job_patient_insert ON integration.file_deletion_job "
        "FOR INSERT TO gutcare_app WITH CHECK "
        "(patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY file_deletion_job_worker_access ON integration.file_deletion_job "
        "FOR ALL TO gutcare_worker USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY file_deletion_job_worker_access ON integration.file_deletion_job")
    op.execute("DROP POLICY file_deletion_job_patient_insert ON integration.file_deletion_job")
    op.execute("ALTER TABLE integration.file_deletion_job NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration.file_deletion_job DISABLE ROW LEVEL SECURITY")
