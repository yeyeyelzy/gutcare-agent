"""Allow the analysis worker role to claim F02 parse requests safely."""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_f02_analysis_worker_claim"
down_revision: str | None = "0027_f03_f04_recognition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE POLICY medical_parse_request_analysis_worker "
        "ON health.medical_parse_request FOR ALL TO gutcare_analysis_worker "
        "USING (true) WITH CHECK (true)"
    )
    op.execute("GRANT SELECT ON health.medical_parse_request TO gutcare_analysis_worker")
    op.execute(
        "GRANT UPDATE (status, claimed_at, finished_at) "
        "ON health.medical_parse_request TO gutcare_analysis_worker"
    )
    op.execute(
        "CREATE POLICY medical_document_analysis_worker_parse_claim "
        "ON health.medical_document FOR UPDATE TO gutcare_analysis_worker "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "GRANT SELECT (id, patient_id, deleted_at) ON health.medical_document "
        "TO gutcare_analysis_worker"
    )
    op.execute("GRANT UPDATE (parse_status) ON health.medical_document TO gutcare_analysis_worker")


def downgrade() -> None:
    op.execute(
        "REVOKE UPDATE (parse_status) ON health.medical_document FROM gutcare_analysis_worker"
    )
    op.execute(
        "REVOKE SELECT (id, patient_id, deleted_at) ON health.medical_document "
        "FROM gutcare_analysis_worker"
    )
    op.execute(
        "DROP POLICY medical_document_analysis_worker_parse_claim ON health.medical_document"
    )
    op.execute(
        "REVOKE UPDATE (status, claimed_at, finished_at) "
        "ON health.medical_parse_request "
        "FROM gutcare_analysis_worker"
    )
    op.execute("REVOKE SELECT ON health.medical_parse_request FROM gutcare_analysis_worker")
    op.execute("DROP POLICY medical_parse_request_analysis_worker ON health.medical_parse_request")
