"""SQLAlchemy models for the frozen F01 account and registration-consent schema."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


JsonDocument = JSON().with_variant(JSONB(), "postgresql")


class UserAccount(Base):
    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_verification', 'active', 'locked', 'deactivated')",
            name="ck_user_account_status",
        ),
        CheckConstraint("failed_login_count >= 0", name="ck_user_account_failed_login_count"),
        Index(
            "uq_user_account_email_lookup_hash_live",
            "email_lookup_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "iam"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    email_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email_lookup_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_token"
    __table_args__ = (
        CheckConstraint("purpose IN ('register', 'password_reset')", name="ck_email_token_purpose"),
        CheckConstraint("attempt_count >= 0", name="ck_email_token_attempt_count"),
        Index("ix_email_token_user_purpose_created", "user_id", "purpose", "created_at"),
        {"schema": "iam"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("iam.user_account.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RefreshSession(Base):
    __tablename__ = "refresh_session"
    __table_args__ = (
        Index("ix_refresh_session_user_active", "user_id", "expires_at"),
        Index("ix_refresh_session_family", "family_id", "revoked_at"),
        UniqueConstraint("replaced_by_session_id", name="uq_refresh_session_successor"),
        {"schema": "iam"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    family_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "iam.refresh_session.id",
            deferrable=True,
            initially="DEFERRED",
            name="fk_refresh_session_family_root",
        ),
        nullable=False,
    )
    parent_session_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("iam.refresh_session.id", ondelete="SET NULL", name="fk_refresh_session_parent"),
    )
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "iam.refresh_session.id", ondelete="SET NULL", name="fk_refresh_session_successor"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("iam.user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    device_id: Mapped[UUID | None] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PatientProfile(Base):
    __tablename__ = "patient_profile"
    __table_args__ = (
        CheckConstraint("birth_year BETWEEN 1900 AND 2100", name="ck_patient_profile_birth_year"),
        CheckConstraint("profile_version >= 1", name="ck_patient_profile_version"),
        UniqueConstraint("user_id", name="uq_patient_profile_user_id"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("iam.user_account.id", ondelete="CASCADE"), nullable=False
    )
    nickname: Mapped[str | None] = mapped_column(String(64))
    avatar_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    birth_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai", server_default="Asia/Shanghai"
    )
    profile_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientConsent(Base):
    __tablename__ = "patient_consent"
    __table_args__ = (
        CheckConstraint(
            "consent_type IN ('privacy_policy', 'health_data_processing', 'sensitive_image', "
            "'third_party_ai', 'push_notification')",
            name="ck_patient_consent_type",
        ),
        Index("ix_patient_consent_current", "patient_id", "consent_type", "decided_at"),
        {"schema": "health"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    patient_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("health.patient_profile.id", ondelete="CASCADE"), nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(48), nullable=False)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JsonDocument)


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_account_deletion_request_status",
        ),
        UniqueConstraint("user_id", name="uq_account_deletion_request_user_id"),
        {"schema": "iam"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("iam.user_account.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending"
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
