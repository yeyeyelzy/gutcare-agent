"""F02 persistence models."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base

# Complete database type map; weight_kg remains a legacy persisted F08 fact, not
# an allowed new F02 Agent candidate field.
MEDICAL_FIELD_TYPE_PAIRS = {
    "diagnosis": "diagnosis",
    "document_date": "date",
    "weight_kg": "decimal",
    "recommendation": "string",
    "test_item": "string",
    "test_result": "object",
    "medication_name": "string",
    "medication_dose": "object",
    "medication_frequency": "string",
    "medication_duration": "string",
    "allergy": "string",
}
AGENT_MEDICAL_FIELD_TYPE_PAIRS = {
    key: value for key, value in MEDICAL_FIELD_TYPE_PAIRS.items() if key != "weight_kg"
}


class UploadSession(Base):
    __tablename__ = "upload_session"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('medical_document', 'diet_image', 'stool_image', 'avatar')",
            name="ck_upload_session_purpose",
        ),
        CheckConstraint(
            "status IN ('issued', 'uploaded', 'completed', 'failed', 'expired')",
            name="ck_upload_session_status",
        ),
        CheckConstraint("expected_size_bytes > 0", name="ck_upload_session_size_positive"),
        ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_upload_session_file_patient",
        ),
        UniqueConstraint("patient_id", "idempotency_key", name="uq_upload_session_idempotency"),
        Index("ix_upload_session_expiry", "status", "expires_at"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("health.patient_profile.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    capability_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="issued")
    file_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FileObject(Base):
    __tablename__ = "file_object"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_file_object_size_positive"),
        CheckConstraint(
            "sensitivity IN ('normal', 'medical', 'sensitive_image')",
            name="ck_file_object_sensitivity",
        ),
        CheckConstraint(
            "scan_status IN ('pending', 'clean', 'rejected', 'failed')",
            name="ck_file_object_scan_status",
        ),
        CheckConstraint(
            "storage_status IN ('uploading', 'available', 'deleting', 'deleted', 'failed')",
            name="ck_file_object_storage_status",
        ),
        CheckConstraint(
            "storage_status <> 'available' OR scan_status = 'clean'",
            name="ck_file_object_available_clean",
        ),
        UniqueConstraint("id", "patient_id", name="uq_file_object_id_patient"),
        UniqueConstraint("bucket_name", "object_key", name="uq_file_object_location"),
        Index("ix_file_object_patient_status", "patient_id", "storage_status", "created_at"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("health.patient_profile.id", ondelete="CASCADE"), nullable=False
    )
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(24), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicalDocument(Base):
    __tablename__ = "medical_document"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('outpatient_record', 'discharge_summary', "
            "'diagnosis_certificate', 'lab_report', 'prescription', 'other')",
            name="ck_medical_document_type",
        ),
        CheckConstraint(
            "processing_mode IN ('store_only', 'analyze')",
            name="ck_medical_document_processing_mode",
        ),
        CheckConstraint(
            "parse_status IN ('not_requested', 'pending', 'processing', "
            "'needs_confirmation', 'confirmed', 'failed')",
            name="ck_medical_document_parse_status",
        ),
        CheckConstraint(
            "parse_outcome IS NULL OR parse_outcome IN "
            "('extracted', 'no_supported_facts', 'insufficient_quality')",
            name="ck_medical_document_parse_outcome",
        ),
        CheckConstraint(
            "parse_reason_code IS NULL OR parse_reason_code IN "
            "('no_supported_fields', 'unsupported_content', 'low_quality_scan', "
            "'illegible_content', 'incomplete_document')",
            name="ck_medical_document_parse_reason_code",
        ),
        CheckConstraint(
            "(parse_outcome IS NULL AND parse_reason_code IS NULL) OR "
            "(parse_outcome = 'extracted' AND parse_reason_code IS NULL) OR "
            "(parse_outcome = 'no_supported_facts' AND parse_reason_code IN "
            "('no_supported_fields', 'unsupported_content')) OR "
            "(parse_outcome = 'insufficient_quality' AND parse_reason_code IN "
            "('low_quality_scan', 'illegible_content', 'incomplete_document'))",
            name="ck_medical_document_parse_outcome_reason_pair",
        ),
        CheckConstraint("record_version >= 1", name="ck_medical_document_version"),
        ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_document_file_patient",
        ),
        Index("ix_medical_document_patient_date", "patient_id", "document_date", "created_at"),
        UniqueConstraint("id", "patient_id", name="uq_medical_document_id_patient"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("health.patient_profile.id", ondelete="CASCADE"), nullable=False
    )
    file_object_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hospital_name: Mapped[str | None] = mapped_column(String(160))
    document_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    processing_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False)
    parse_outcome: Mapped[str | None] = mapped_column(String(32))
    parse_reason_code: Mapped[str | None] = mapped_column(String(32))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicalParseRequest(Base):
    __tablename__ = "medical_parse_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'needs_confirmation', 'succeeded', 'failed', "
            "'cancelled', 'invalidated')",
            name="ck_medical_parse_request_status",
        ),
        CheckConstraint("record_version >= 1", name="ck_medical_parse_request_version"),
        CheckConstraint(
            "parse_outcome IS NULL OR parse_outcome IN "
            "('extracted', 'no_supported_facts', 'insufficient_quality')",
            name="ck_medical_parse_request_outcome",
        ),
        CheckConstraint(
            "parse_reason_code IS NULL OR parse_reason_code IN "
            "('no_supported_fields', 'unsupported_content', 'low_quality_scan', "
            "'illegible_content', 'incomplete_document')",
            name="ck_medical_parse_request_reason_code",
        ),
        CheckConstraint(
            "(parse_outcome IS NULL AND parse_reason_code IS NULL) OR "
            "(parse_outcome = 'extracted' AND parse_reason_code IS NULL "
            "AND status IN ('needs_confirmation', 'succeeded', 'invalidated')) OR "
            "(parse_outcome = 'no_supported_facts' AND parse_reason_code IN "
            "('no_supported_fields', 'unsupported_content') "
            "AND status IN ('succeeded', 'invalidated')) OR "
            "(parse_outcome = 'insufficient_quality' AND parse_reason_code IN "
            "('low_quality_scan', 'illegible_content', 'incomplete_document') "
            "AND status IN ('succeeded', 'invalidated'))",
            name="ck_medical_parse_request_outcome_reason_pair",
        ),
        ForeignKeyConstraint(
            ["document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_parse_request_document_patient",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_parse_request_file_patient",
        ),
        UniqueConstraint(
            "document_id", "record_version", name="uq_medical_parse_request_document_version"
        ),
        UniqueConstraint("id", "patient_id", name="uq_medical_parse_request_id_patient"),
        UniqueConstraint("id", "callback_id", name="uq_medical_parse_request_callback"),
        Index("ix_medical_parse_request_claim", "status", "created_at"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(Uuid)
    file_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    callback_id: Mapped[UUID | None] = mapped_column(Uuid)
    callback_hash: Mapped[str | None] = mapped_column(CHAR(64))
    parse_outcome: Mapped[str | None] = mapped_column(String(32))
    parse_reason_code: Mapped[str | None] = mapped_column(String(32))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicalFieldCandidate(Base):
    __tablename__ = "medical_field_candidate"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('string','date','decimal','integer','boolean','diagnosis','object')",
            name="ck_medical_candidate_value_type",
        ),
        CheckConstraint(
            "(field_code = 'diagnosis' AND value_type = 'diagnosis') OR "
            "(field_code = 'document_date' AND value_type = 'date') OR "
            "(field_code = 'weight_kg' AND value_type = 'decimal') OR "
            "(field_code IN ('recommendation','test_item','medication_name',"
            "'medication_frequency','medication_duration','allergy') AND value_type = 'string') OR "
            "(field_code IN ('test_result','medication_dose') AND value_type = 'object')",
            name="ck_medical_candidate_field_type",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'accepted', 'corrected', 'rejected', 'invalidated')",
            name="ck_medical_field_candidate_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_medical_field_candidate_confidence",
        ),
        ForeignKeyConstraint(
            ["request_id", "patient_id"],
            ["health.medical_parse_request.id", "health.medical_parse_request.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_candidate_request_patient",
        ),
        UniqueConstraint("id", "patient_id", name="uq_medical_candidate_id_patient"),
        Index("ix_medical_candidate_patient_request", "patient_id", "request_id", "review_status"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_code: Mapped[str] = mapped_column(String(48), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column()
    uncertainty: Mapped[str | None] = mapped_column(String(500))
    source_locator: Mapped[Any] = mapped_column(JSON)
    excerpt: Mapped[str | None] = mapped_column(String(500))
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConfirmedMedicalFact(Base):
    __tablename__ = "confirmed_medical_fact"
    __table_args__ = (
        CheckConstraint(
            "fact_status IN ('active', 'rejected', 'superseded', 'source_deleted')",
            name="ck_confirmed_medical_fact_status",
        ),
        ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="RESTRICT",
            name="fk_confirmed_fact_candidate_patient",
        ),
        UniqueConstraint("candidate_id", name="uq_confirmed_fact_candidate"),
        UniqueConstraint("id", "patient_id", name="uq_confirmed_fact_id_patient"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_code: Mapped[str] = mapped_column(String(48), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    fact_status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MedicalFactConflict(Base):
    __tablename__ = "medical_fact_conflict"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'invalidated')",
            name="ck_medical_fact_conflict_status",
        ),
        CheckConstraint("record_version >= 1", name="ck_medical_fact_conflict_version"),
        CheckConstraint(
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
        ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        UniqueConstraint("id", "patient_id", name="uq_medical_fact_conflict_id_patient"),
        UniqueConstraint(
            "patient_id", "resolution_key", name="uq_medical_fact_conflict_resolution_key"
        ),
        Index("ix_medical_fact_conflict_patient_status", "patient_id", "status", "created_at"),
        Index(
            "uq_medical_fact_conflict_patient_group_active",
            "patient_id",
            "group_hash",
            unique=True,
            postgresql_where=text("status <> 'invalidated'"),
        ),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    group_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    membership_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    resolution: Mapped[str | None] = mapped_column(String(24))
    resolution_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(CHAR(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason_code: Mapped[str | None] = mapped_column(String(32))
    invalidated_source_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MedicalFactConflictMember(Base):
    __tablename__ = "medical_fact_conflict_member"
    __table_args__ = (
        CheckConstraint(
            "member_role IN ('test_item', 'test_result')", name="ck_medical_conflict_member_role"
        ),
        CheckConstraint(
            "fact_version >= 1 AND document_version >= 1",
            name="ck_medical_conflict_member_versions",
        ),
        ForeignKeyConstraint(
            ["conflict_id", "patient_id"],
            ["health.medical_fact_conflict.id", "health.medical_fact_conflict.patient_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["fact_id", "patient_id"],
            ["health.confirmed_medical_fact.id", "health.confirmed_medical_fact.patient_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "conflict_id", "patient_id", "fact_id", name="uq_medical_conflict_member_fact"
        ),
        UniqueConstraint(
            "conflict_id",
            "patient_id",
            "document_id",
            "member_role",
            name="uq_medical_conflict_member_document_role",
        ),
        Index("ix_medical_conflict_member_patient_fact", "patient_id", "fact_id"),
        {"schema": "health"},
    )

    conflict_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    member_role: Mapped[str] = mapped_column(String(16), nullable=False)
    fact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MedicalCandidateDecision(Base):
    __tablename__ = "medical_candidate_decision"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('accept', 'correct', 'reject')", name="ck_medical_candidate_decision"
        ),
        ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_candidate_decision_patient",
        ),
        UniqueConstraint(
            "patient_id", "idempotency_key", name="uq_medical_candidate_decision_idempotency"
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    chosen_value: Mapped[Any] = mapped_column(JSON)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MedicalCandidateDecisionIdempotency(Base):
    __tablename__ = "medical_candidate_decision_idempotency"
    __table_args__ = (
        CheckConstraint("response_status = 204", name="ck_medical_decision_idempotency_status"),
        ForeignKeyConstraint(
            ["candidate_id", "patient_id"],
            ["health.medical_field_candidate.id", "health.medical_field_candidate.patient_id"],
            ondelete="CASCADE",
            name="fk_medical_decision_idempotency_candidate_patient",
        ),
        UniqueConstraint(
            "patient_id", "idempotency_key", name="uq_medical_decision_idempotency_key"
        ),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False, server_default="204")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FileDownloadGrant(Base):
    __tablename__ = "file_download_grant"
    __table_args__ = (
        ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_file_download_grant_file_patient",
        ),
        Index("ix_file_download_grant_expiry", "expires_at"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("health.patient_profile.id", ondelete="CASCADE"), nullable=False
    )
    file_object_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FileDeletionJob(Base):
    __tablename__ = "file_deletion_job"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing')", name="ck_file_deletion_job_status"),
        CheckConstraint("attempts >= 0", name="ck_file_deletion_job_attempts"),
        ForeignKeyConstraint(
            ["file_object_id", "patient_id"],
            ["health.file_object.id", "health.file_object.patient_id"],
            ondelete="CASCADE",
            name="fk_file_deletion_job_file_patient",
        ),
        UniqueConstraint("file_object_id", name="uq_file_deletion_job_file"),
        Index("ix_file_deletion_job_due", "status", "due_at"),
        {"schema": "integration"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    file_object_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FileOrphanCleanupJob(Base):
    __tablename__ = "file_orphan_cleanup_job"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_file_orphan_cleanup_attempts"),
        CheckConstraint(
            "status IN ('pending', 'processing')", name="ck_file_orphan_cleanup_status"
        ),
        UniqueConstraint("bucket_name", "object_key", name="uq_file_orphan_cleanup_location"),
        Index("ix_file_orphan_cleanup_due", "status", "due_at"),
        Index("ix_file_orphan_cleanup_lease", "status", "locked_at"),
        {"schema": "integration"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID | None] = mapped_column(Uuid)
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
