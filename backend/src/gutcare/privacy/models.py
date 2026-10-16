"""Persistence models for durable F13 operations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, DateTime, Integer, LargeBinary, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from gutcare.auth.models import Base


class DeletionOperation(Base):
    __tablename__ = "deletion_operation"
    __table_args__ = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    account_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    patient_id: Mapped[UUID | None] = mapped_column(Uuid)
    receipt_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(48))


class DeletionStep(Base):
    __tablename__ = "deletion_step"
    __table_args__ = {"schema": "privacy"}

    operation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    step_code: Mapped[str] = mapped_column(String(48), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(48))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ObjectInventory(Base):
    __tablename__ = "object_inventory"
    __table_args__ = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    operation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512))
    version_id: Mapped[str | None] = mapped_column(String(256))
    key_digest_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(48))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportOperation(Base):
    __tablename__ = "export_operation"
    __table_args__ = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="preview")
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512))
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary)
    capability_hash: Mapped[str | None] = mapped_column(CHAR(64))
    capability_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capability_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(48))
