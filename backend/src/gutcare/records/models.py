"""F03-F05 patient record persistence models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class DietRecord(Base):
    __tablename__ = "diet_record"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_diet_record_id_patient"),
        Index("ix_diet_record_patient_occurred", "patient_id", "occurred_at"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    image_set_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meal_type: Mapped[str | None] = mapped_column(String(24))
    text_description: Mapped[str | None] = mapped_column(Text)
    portion_note: Mapped[str | None] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="patient_manual"
    )
    confirmation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="confirmed"
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DietItem(Base):
    __tablename__ = "diet_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["diet_record_id", "patient_id"],
            ["health.diet_record.id", "health.diet_record.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    diet_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    item_position: Mapped[int] = mapped_column(Integer, nullable=False)
    category_code: Mapped[str | None] = mapped_column(String(64))
    amount_text: Mapped[str | None] = mapped_column(String(160))
    source_recognition_request_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_candidate_group_key: Mapped[UUID | None] = mapped_column(Uuid)
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="patient_manual"
    )
    confirmed_by_patient: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class StoolRecord(Base):
    __tablename__ = "stool_record"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_stool_record_id_patient"),
        CheckConstraint(
            "bristol_type IS NULL OR bristol_type BETWEEN 1 AND 7", name="ck_stool_bristol"
        ),
        Index("ix_stool_record_patient_occurred", "patient_id", "occurred_at"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    image_set_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bristol_type: Mapped[int | None] = mapped_column(SmallInteger)
    color_code: Mapped[str | None] = mapped_column(String(32))
    blood_reported: Mapped[bool | None] = mapped_column(Boolean)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="patient_manual"
    )
    confirmation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="confirmed"
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SymptomRecord(Base):
    __tablename__ = "symptom_record"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_symptom_record_id_patient"),
        CheckConstraint(
            "symptom_status IN ('ongoing','relieved')", name="ck_symptom_record_status"
        ),
        Index("ix_symptom_record_patient_occurred", "patient_id", "occurred_at"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    symptom_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="ongoing"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="patient_manual"
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SymptomItem(Base):
    __tablename__ = "symptom_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["symptom_record_id", "patient_id"],
            ["health.symptom_record.id", "health.symptom_record.patient_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "severity IS NULL OR severity BETWEEN 0 AND 10", name="ck_symptom_severity"
        ),
        CheckConstraint(
            "symptom_code IN ('abdominal_pain','bloating','diarrhea','constipation','nausea',"
            "'vomiting','acid_reflux','appetite_change','blood_in_stool_concern','other')",
            name="ck_symptom_code",
        ),
        CheckConstraint(
            "(symptom_code = 'other' AND other_description IS NOT NULL AND "
            "length(btrim(other_description)) BETWEEN 1 AND 160) OR "
            "(symptom_code <> 'other' AND other_description IS NULL)",
            name="ck_symptom_other_description",
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    symptom_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    symptom_code: Mapped[str] = mapped_column(String(48), nullable=False)
    other_description: Mapped[str | None] = mapped_column(String(160))
    severity: Mapped[int | None] = mapped_column(SmallInteger)
    body_location: Mapped[str | None] = mapped_column(String(64))
    patient_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class SymptomStatusEvent(Base):
    __tablename__ = "symptom_status_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["symptom_record_id", "patient_id"],
            ["health.symptom_record.id", "health.symptom_record.patient_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('ongoing','relieved')", name="ck_symptom_status_event"),
        Index(
            "ix_symptom_status_event_patient_record_time",
            "patient_id",
            "symptom_record_id",
            "changed_at",
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    symptom_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RecordIdempotency(Base):
    __tablename__ = "record_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "operation", "idempotency_key", name="uq_record_idempotency_scope"
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RiskRule(Base):
    __tablename__ = "risk_rule"
    __table_args__ = (
        UniqueConstraint("rule_code", "version", name="uq_risk_rule_code_version"),
        {"schema": "safety"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False)
    environment: Mapped[str] = mapped_column(String(24), nullable=False, server_default="test_only")
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_refs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RiskAlert(Base):
    __tablename__ = "risk_alert"
    __table_args__ = (
        UniqueConstraint("patient_id", "deduplication_key", name="uq_risk_alert_patient_dedup"),
        UniqueConstraint("id", "patient_id", name="uq_risk_alert_id_patient"),
        Index("ix_risk_alert_patient_status_time", "patient_id", "status", "triggered_at"),
        {"schema": "safety"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    rule_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("safety.risk_rule.id"), nullable=False)
    source_record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="unread")
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reevaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AlertEvidence(Base):
    __tablename__ = "alert_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["alert_id", "patient_id"],
            ["safety.risk_alert.id", "safety.risk_alert.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "safety"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    alert_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    record_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    field_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
