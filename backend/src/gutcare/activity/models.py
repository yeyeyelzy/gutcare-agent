"""F07 patient activity persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class ActivityRecord(Base):
    __tablename__ = "activity_record"
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('walking','jogging','cycling','other')", name="ck_activity_type"
        ),
        CheckConstraint(
            "(activity_type = 'other' AND description IS NOT NULL AND "
            "length(btrim(description)) BETWEEN 1 AND 160) OR "
            "(activity_type <> 'other' AND description IS NULL)",
            name="ck_activity_other_description",
        ),
        CheckConstraint("intensity IN ('low','moderate','high')", name="ck_activity_intensity"),
        CheckConstraint(
            "subjective_feeling IN ('better','same','worse')", name="ck_activity_feeling"
        ),
        CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="ck_activity_duration"),
        ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        Index("ix_activity_record_patient_occurred", "patient_id", "occurred_at"),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(String(160))
    intensity: Mapped[str] = mapped_column(String(16), nullable=False)
    subjective_feeling: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
