"""F12 patient notifications and outbox persistence."""

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    Time,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preference"
    __table_args__ = ({"schema": "health"},)
    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    ordinary_in_app_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    quiet_start: Mapped[time | None] = mapped_column(Time)
    quiet_end: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = ({"schema": "health"},)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientNotification(Base):
    __tablename__ = "patient_notification"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outbox_id", "patient_id"],
            ["health.notification_outbox.id", "health.notification_outbox.patient_id"],
        ),
        {"schema": "health"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    outbox_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[UUID | None] = mapped_column(Uuid)
    target_unavailable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
