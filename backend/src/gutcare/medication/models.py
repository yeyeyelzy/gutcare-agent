"""F06 medication persistence models."""

from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class MedicationSourceRef(Base):
    __tablename__ = "medication_source_ref"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_med_source_ref_id_patient"),
        ForeignKeyConstraint(
            ["live_document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="RESTRICT",
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    live_document_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicationPlan(Base):
    __tablename__ = "medication_plan"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_med_plan_id_patient"),
        CheckConstraint(
            "(source_type = 'manual' AND source_ref_id IS NULL) OR "
            "(source_type = 'medical_document' AND source_ref_id IS NOT NULL)",
            name="ck_med_plan_source_ref",
        ),
        ForeignKeyConstraint(
            ["source_ref_id", "patient_id"],
            ["health.medication_source_ref.id", "health.medication_source_ref.patient_id"],
        ),
        Index("ix_med_plan_patient_status", "patient_id", "plan_status"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    medication_name: Mapped[str] = mapped_column(String(160), nullable=False)
    dosage_text: Mapped[str | None] = mapped_column(String(160))
    route_code: Mapped[str | None] = mapped_column(String(32))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_ref_id: Mapped[UUID | None] = mapped_column(Uuid)
    confirmation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    plan_status: Mapped[str] = mapped_column(String(24), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicationSchedule(Base):
    __tablename__ = "medication_schedule"
    __table_args__ = (
        ForeignKeyConstraint(
            ["plan_id", "patient_id"],
            ["health.medication_plan.id", "health.medication_plan.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "patient_id", name="uq_med_schedule_id_patient"),
        Index("ix_med_schedule_patient_plan", "patient_id", "plan_id"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    plan_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    local_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    rrule: Mapped[str | None] = mapped_column(String, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicationCheckin(Base):
    __tablename__ = "medication_checkin"
    __table_args__ = (
        ForeignKeyConstraint(
            ["schedule_id", "patient_id"],
            ["health.medication_schedule.id", "health.medication_schedule.patient_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("schedule_id", "local_date", name="uq_med_checkin_schedule_local_date"),
        Index("ix_med_checkin_patient_scheduled", "patient_id", "scheduled_for"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    schedule_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MedicationIdempotency(Base):
    __tablename__ = "medication_idempotency"
    __table_args__ = (
        UniqueConstraint("patient_id", "route", "idempotency_key", name="uq_med_idempotency_scope"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
