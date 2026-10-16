"""Add private file upload sessions, medical documents and download grants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_f02_files_medical_documents"
down_revision: str | None = "0004_account_deletion_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_patient_rls(table: str) -> None:
    op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON health.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")
    op.execute("GRANT USAGE ON SCHEMA integration TO gutcare_app, gutcare_worker")
    op.create_table(
        "upload_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("bucket_name", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("capability_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), server_default="issued", nullable=False),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "purpose IN ('medical_document', 'diet_image', 'stool_image', 'avatar')",
            name="ck_upload_session_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('issued', 'uploaded', 'completed', 'failed', 'expired')",
            name="ck_upload_session_status",
        ),
        sa.CheckConstraint("expected_size_bytes > 0", name="ck_upload_session_size_positive"),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("patient_id", "idempotency_key", name="uq_upload_session_idempotency"),
        schema="health",
    )
    op.create_index(
        "ix_upload_session_expiry", "upload_session", ["status", "expires_at"], schema="health"
    )

    op.create_table(
        "file_object",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_name", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("sensitivity", sa.String(24), nullable=False),
        sa.Column("scan_status", sa.String(24), nullable=False),
        sa.Column("storage_status", sa.String(24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("size_bytes > 0", name="ck_file_object_size_positive"),
        sa.CheckConstraint(
            "sensitivity IN ('normal', 'medical', 'sensitive_image')",
            name="ck_file_object_sensitivity",
        ),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'rejected', 'failed')",
            name="ck_file_object_scan_status",
        ),
        sa.CheckConstraint(
            "storage_status IN ('uploading', 'available', 'deleting', 'deleted', 'failed')",
            name="ck_file_object_storage_status",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "patient_id", name="uq_file_object_id_patient"),
        sa.UniqueConstraint("bucket_name", "object_key", name="uq_file_object_location"),
        schema="health",
    )
    op.create_index(
        "ix_file_object_patient_status",
        "file_object",
        ["patient_id", "storage_status", "created_at"],
        schema="health",
    )

    op.create_table(
        "medical_document",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("hospital_name", sa.String(160)),
        sa.Column("document_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("processing_mode", sa.String(16), nullable=False),
        sa.Column("parse_status", sa.String(24), nullable=False),
        sa.Column("record_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "document_type IN ('outpatient_record', 'discharge_summary', "
            "'diagnosis_certificate', 'lab_report', 'prescription', 'other')",
            name="ck_medical_document_type",
        ),
        sa.CheckConstraint(
            "processing_mode IN ('store_only', 'analyze')",
            name="ck_medical_document_processing_mode",
        ),
        sa.CheckConstraint(
            "parse_status IN ('not_requested', 'pending', 'processing', "
            "'needs_confirmation', 'confirmed', 'failed')",
            name="ck_medical_document_parse_status",
        ),
        sa.CheckConstraint("record_version >= 1", name="ck_medical_document_version"),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 1000", name="ck_medical_document_notes_length"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_document_file_patient",
        ),
        sa.UniqueConstraint("file_object_id", name="uq_medical_document_file_object"),
        schema="health",
    )
    op.create_index(
        "ix_medical_document_patient_date",
        "medical_document",
        ["patient_id", "document_date", "created_at"],
        schema="health",
    )

    op.create_table(
        "file_download_grant",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_file_download_grant_file_patient",
        ),
        schema="health",
    )
    op.create_index(
        "ix_file_download_grant_expiry", "file_download_grant", ["expires_at"], schema="health"
    )

    op.create_table(
        "file_deletion_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_name", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing')", name="ck_file_deletion_job_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_file_deletion_job_attempts"),
        sa.ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_file_deletion_job_file_patient",
        ),
        sa.UniqueConstraint("file_object_id", name="uq_file_deletion_job_file"),
        schema="integration",
    )
    op.create_index(
        "ix_file_deletion_job_due", "file_deletion_job", ["status", "due_at"], schema="integration"
    )

    for table in ("upload_session", "file_object", "medical_document", "file_download_grant"):
        _enable_patient_rls(table)
    op.execute("DROP POLICY file_download_grant_patient_isolation ON health.file_download_grant")
    op.execute(
        "CREATE POLICY file_download_grant_scope ON health.file_download_grant "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid "
        "OR token_hash = NULLIF(current_setting('app.download_capability_hash', true), '')) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    patient_file_tables = (
        "health.upload_session, health.file_object, health.medical_document, "
        "health.file_download_grant"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {patient_file_tables} TO gutcare_app")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {patient_file_tables} TO gutcare_worker")
    op.execute("GRANT INSERT ON integration.file_deletion_job TO gutcare_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON integration.file_deletion_job TO gutcare_worker"
    )


def downgrade() -> None:
    op.drop_index("ix_file_deletion_job_due", table_name="file_deletion_job", schema="integration")
    op.drop_table("file_deletion_job", schema="integration")
    for table in ("upload_session", "file_object", "medical_document", "file_download_grant"):
        policy = (
            "file_download_grant_scope"
            if table == "file_download_grant"
            else f"{table}_patient_isolation"
        )
        op.execute(f"DROP POLICY {policy} ON health.{table}")
    op.drop_index(
        "ix_file_download_grant_expiry", table_name="file_download_grant", schema="health"
    )
    op.drop_table("file_download_grant", schema="health")
    op.drop_index(
        "ix_medical_document_patient_date", table_name="medical_document", schema="health"
    )
    op.drop_table("medical_document", schema="health")
    op.drop_index("ix_file_object_patient_status", table_name="file_object", schema="health")
    op.drop_table("file_object", schema="health")
    op.drop_index("ix_upload_session_expiry", table_name="upload_session", schema="health")
    op.drop_table("upload_session", schema="health")
    op.execute("DROP SCHEMA integration")
