"""Persistence model for patient-owned mood records."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class MoodRecord(Base):
    __tablename__ = "mood_record"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_mood_record_id_patient"),
        CheckConstraint("mood_level BETWEEN 1 AND 5", name="ck_mood_record_level"),
        CheckConstraint("record_version >= 1", name="ck_mood_record_version"),
        CheckConstraint(
            "health.is_valid_mood_emotion_tags(emotion_tags)", name="ck_mood_record_emotion_tags"
        ),
        ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        Index(
            "ix_mood_record_patient_occurred_active",
            "patient_id",
            text("occurred_at DESC"),
            text("id DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mood_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    emotion_tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(String(500))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
