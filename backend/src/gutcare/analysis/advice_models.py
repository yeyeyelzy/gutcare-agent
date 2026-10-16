"""F09 advice persistence models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
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


class HealthAdvice(Base):
    __tablename__ = "health_advice"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_health_advice_id_patient"),
        ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    safety_boundary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="new")
    basis_updated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    basis_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    basis_update_reason: Mapped[str | None] = mapped_column(String(32))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdviceEvidence(Base):
    __tablename__ = "advice_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    advice_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_version: Mapped[int | None] = mapped_column(Integer)
    locator: Mapped[str | None] = mapped_column(String(160))
    source_deleted: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    knowledge_ref: Mapped[str | None] = mapped_column(String(160))
    knowledge_version: Mapped[str | None] = mapped_column(String(64))
    knowledge_title: Mapped[str | None] = mapped_column(String(240))
    knowledge_publisher: Mapped[str | None] = mapped_column(String(160))
    citation_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdviceCallback(Base):
    __tablename__ = "advice_callback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("task_id", "callback_id", name="uq_advice_callback_task_id"),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    callback_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdviceFeedback(Base):
    __tablename__ = "advice_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("advice_id", "patient_id", name="uq_advice_feedback_current"),
        {"schema": "analysis"},
    )
    advice_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    feedback_type: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdviceFeedbackEvent(Base):
    __tablename__ = "advice_feedback_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["advice_id", "patient_id"],
            ["analysis.health_advice.id", "analysis.health_advice.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("patient_id", "idempotency_key", name="uq_advice_feedback_event_key"),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    advice_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
