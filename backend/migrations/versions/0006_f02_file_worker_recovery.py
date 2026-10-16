"""Add F02 ownership and worker recovery constraints."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_f02_file_worker_recovery"
down_revision: str | None = "0005_f02_files_medical_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_upload_session_file_patient",
        "upload_session",
        "file_object",
        ["file_object_id", "patient_id"],
        ["id", "patient_id"],
        source_schema="health",
        referent_schema="health",
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_file_object_available_clean",
        "file_object",
        "storage_status <> 'available' OR scan_status = 'clean'",
        schema="health",
    )
    op.add_column(
        "file_deletion_job",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        schema="integration",
    )
    op.create_index(
        "ix_file_deletion_job_lease",
        "file_deletion_job",
        ["status", "locked_at"],
        schema="integration",
    )
    op.execute(
        "CREATE POLICY upload_session_worker_access ON health.upload_session "
        "FOR ALL TO gutcare_worker USING (true) WITH CHECK (true)"
    )
    op.create_table(
        "file_orphan_cleanup_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("bucket_name", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("reason", sa.String(48), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_file_orphan_cleanup_attempts"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing')", name="ck_file_orphan_cleanup_status"
        ),
        sa.UniqueConstraint("bucket_name", "object_key", name="uq_file_orphan_cleanup_location"),
        schema="integration",
    )
    op.create_index(
        "ix_file_orphan_cleanup_due",
        "file_orphan_cleanup_job",
        ["status", "due_at"],
        schema="integration",
    )
    op.create_index(
        "ix_file_orphan_cleanup_lease",
        "file_orphan_cleanup_job",
        ["status", "locked_at"],
        schema="integration",
    )
    op.execute("GRANT INSERT ON integration.file_orphan_cleanup_job TO gutcare_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON integration.file_orphan_cleanup_job TO gutcare_worker"
    )


def downgrade() -> None:
    op.execute("DROP POLICY upload_session_worker_access ON health.upload_session")
    op.drop_index(
        "ix_file_orphan_cleanup_lease",
        table_name="file_orphan_cleanup_job",
        schema="integration",
    )
    op.drop_index(
        "ix_file_orphan_cleanup_due",
        table_name="file_orphan_cleanup_job",
        schema="integration",
    )
    op.drop_table("file_orphan_cleanup_job", schema="integration")
    op.drop_index(
        "ix_file_deletion_job_lease", table_name="file_deletion_job", schema="integration"
    )
    op.drop_column("file_deletion_job", "locked_at", schema="integration")
    op.drop_constraint(
        "ck_file_object_available_clean", "file_object", schema="health", type_="check"
    )
    op.drop_constraint(
        "fk_upload_session_file_patient", "upload_session", schema="health", type_="foreignkey"
    )
