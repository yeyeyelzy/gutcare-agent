"""F08 task and immutable snapshot persistence models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    DateTime,
    ForeignKeyConstraint,
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


class AnalysisTask(Base):
    __tablename__ = "analysis_task"
    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_analysis_task_id_patient"),
        ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    requested_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    retry_of: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TaskInputSnapshot(Base):
    __tablename__ = "task_input_snapshot"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "analysis"},
    )
    task_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalysisTaskIdempotency(Base):
    __tablename__ = "analysis_task_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "route", "idempotency_key", name="uq_analysis_idempotency_scope"
        ),
        ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="202")


class AnalysisTaskCallback(Base):
    __tablename__ = "analysis_task_callback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "patient_id"],
            ["analysis.analysis_task.id", "analysis.analysis_task.patient_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("task_id", "callback_id", name="uq_analysis_task_callback"),
        {"schema": "analysis"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    callback_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    callback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="204")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
