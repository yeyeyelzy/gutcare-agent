"""Privacy operation receipt and patient-scoped export orchestration."""

# ruff: noqa: E501 -- these SQL statements mirror the explicit migration contract.

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.service import AuthContext
from gutcare.files.storage import ObjectStorage
from gutcare.privacy.models import DeletionOperation, ExportOperation
from gutcare.shared.errors import Problem

EXPORT_CATEGORIES = frozenset(
    {
        "profile",
        "consents",
        "medical_documents",
        "files",
        "diet",
        "stool",
        "symptoms",
        "medication",
        "activity",
        "mood",
        "analysis",
        "advice",
        "alerts",
        "notifications",
    }
)
MAX_EXPORT_BYTES = 100 * 1024 * 1024
MAX_EXPORT_CIPHERTEXT_BYTES = MAX_EXPORT_BYTES + 28  # 12-byte nonce + 16-byte GCM tag


def _validate_export_size(ciphertext_size: int, plaintext_size: int | None = None) -> None:
    if ciphertext_size < 28 or ciphertext_size > MAX_EXPORT_CIPHERTEXT_BYTES:
        raise ValueError("Export ciphertext size outside configured bound")
    if plaintext_size is not None and plaintext_size > MAX_EXPORT_BYTES:
        raise ValueError("Export plaintext size outside configured bound")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class PrivacyService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        receipt_pepper: str,
        storage: ObjectStorage | None = None,
        encryption_key: bytes | None = None,
        bucket: str = "gutcare-files",
    ) -> None:
        self._sessions = sessions
        self._pepper = receipt_pepper.encode()
        self._storage = storage
        self._encryption_key = encryption_key
        self._bucket = bucket

    def request_deletion(self, context: AuthContext) -> tuple[UUID, str | None]:
        now = datetime.now(UTC)
        receipt = secrets.token_urlsafe(48)
        account_hash = hmac.new(
            self._pepper, str(context.user_id).encode(), hashlib.sha256
        ).hexdigest()
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.user_id', :id, true)"), {"id": str(context.user_id)}
            )
            db.execute(
                text("SELECT set_config('app.account_hash', :hash, true)"),
                {"hash": account_hash},
            )
            account = (
                db.execute(
                    text("SELECT id, status FROM iam.user_account WHERE id=:id FOR UPDATE"),
                    {"id": context.user_id},
                )
                .mappings()
                .one_or_none()
            )
            if account is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            existing = db.scalar(
                select(DeletionOperation)
                .where(
                    DeletionOperation.account_hash == account_hash,
                    DeletionOperation.status != "completed",
                )
                .with_for_update()
            )
            if existing is not None:
                # The one-time receipt is only returned by the transaction that created
                # the operation. A retry reuses the operation without invalidating it.
                return existing.id, None
            if account["status"] != "active":
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            profile = db.execute(
                text(
                    "SELECT id FROM health.patient_profile WHERE user_id=:id AND deleted_at IS NULL"
                ),
                {"id": context.user_id},
            ).scalar_one_or_none()
            if profile is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(profile)})
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended('gutcare.patient-consent-fence:' || :id, 0))"
                ),
                {"id": str(profile)},
            )
            db.add(
                DeletionOperation(
                    account_hash=account_hash,
                    patient_id=profile,
                    receipt_hash=_digest(receipt),
                    status="pending",
                    requested_at=now,
                    due_at=now + timedelta(days=30),
                )
            )
            db.execute(
                text(
                    "UPDATE iam.user_account SET status='deactivated', updated_at=:now WHERE id=:id"
                ),
                {"id": context.user_id, "now": now},
            )
            db.execute(
                text(
                    "UPDATE iam.refresh_session SET revoked_at=:now WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"id": context.user_id, "now": now},
            )
            db.execute(
                text(
                    "INSERT INTO health.patient_consent (patient_id, consent_type, document_version, granted, decided_at, revoked_at, metadata) SELECT patient_id, consent_type, document_version, false, :now, :now, jsonb_set(COALESCE(metadata, '{}'::jsonb), '{channel}', '\"account_deletion\"'::jsonb) FROM (SELECT DISTINCT ON (consent_type) patient_id, consent_type, document_version, metadata FROM health.patient_consent WHERE patient_id=:patient AND granted=true ORDER BY consent_type, decided_at DESC, id DESC) latest"
                ),
                {"patient": profile, "now": now},
            )
            db.execute(
                text(
                    "UPDATE analysis.analysis_task SET status='cancelled', lease_expires_at=NULL, updated_at=:now WHERE patient_id=:patient AND status IN ('pending','processing')"
                ),
                {"patient": profile, "now": now},
            )
            db.execute(
                text(
                    "UPDATE health.file_download_grant SET expires_at=:now WHERE patient_id=:patient AND expires_at>:now"
                ),
                {"patient": profile, "now": now},
            )
            db.execute(
                text(
                    "UPDATE health.upload_session SET status='expired', expires_at=:now WHERE patient_id=:patient AND status IN ('issued','uploaded')"
                ),
                {"patient": profile, "now": now},
            )
            db.execute(
                text(
                    "UPDATE health.medical_parse_request SET status='invalidated', finished_at=:now WHERE patient_id=:patient AND status IN ('pending','processing','needs_confirmation')"
                ),
                {"patient": profile, "now": now},
            )
            db.execute(
                text(
                    "UPDATE health.medical_field_candidate SET excerpt=NULL, source_locator=NULL, review_status='invalidated' WHERE patient_id=:patient AND review_status='pending'"
                ),
                {"patient": profile},
            )
            db.execute(
                text(
                    "UPDATE privacy.export_operation SET status='cancelled', capability_hash=NULL WHERE patient_id=:patient AND status IN ('preview','pending','processing','ready')"
                ),
                {"patient": profile, "now": now},
            )
            db.flush()
            operation_id = db.scalar(
                select(DeletionOperation.id).where(
                    DeletionOperation.receipt_hash == _digest(receipt)
                )
            )
        if operation_id is None:
            raise RuntimeError("Deletion operation was not persisted")
        return operation_id, receipt

    def deletion_status(self, operation_id: UUID, receipt: str) -> dict[str, object]:
        with self._sessions() as db:
            receipt_hash = _digest(receipt)
            db.execute(
                text("SELECT set_config('app.receipt_hash', :hash, true)"), {"hash": receipt_hash}
            )
            operation = db.scalar(
                select(DeletionOperation).where(
                    DeletionOperation.id == operation_id,
                    DeletionOperation.receipt_hash == receipt_hash,
                )
            )
            if operation is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return {
                "operation_id": operation.id,
                "status": operation.status,
                "requested_at": operation.requested_at,
                "due_at": operation.due_at,
                "completed_at": operation.completed_at,
            }

    @staticmethod
    def _patient_context(db: Session, context: AuthContext) -> UUID:
        db.execute(
            text("SELECT set_config('app.user_id', :id, true)"),
            {"id": str(context.user_id)},
        )
        patient_id = db.execute(
            text("SELECT id FROM health.patient_profile WHERE user_id=:id AND deleted_at IS NULL"),
            {"id": context.user_id},
        ).scalar_one_or_none()
        if patient_id is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Patient not found")
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_id)})
        return patient_id

    def create_export_preview(
        self, context: AuthContext, categories: list[str]
    ) -> tuple[UUID, list[str]]:
        if self._encryption_key is None:
            raise Problem(503, "SERVICE_UNAVAILABLE", "Encrypted export is unavailable")
        normalized = sorted(set(categories))
        if not normalized or set(normalized) - EXPORT_CATEGORIES:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported export category")
        with self._sessions.begin() as db:
            patient_id = self._patient_context(db, context)
            row = ExportOperation(patient_id=patient_id, categories=normalized, status="preview")
            db.add(row)
            db.flush()
            return row.id, normalized

    def confirm_export(self, context: AuthContext, export_id: UUID) -> None:
        if self._encryption_key is None:
            raise Problem(503, "SERVICE_UNAVAILABLE", "Encrypted export is unavailable")
        with self._sessions.begin() as db:
            patient_id = self._patient_context(db, context)
            row = db.scalar(
                select(ExportOperation)
                .where(ExportOperation.id == export_id, ExportOperation.patient_id == patient_id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Export not found")
            if row.status != "preview":
                raise Problem(409, "IDEMPOTENCY_CONFLICT", "Export cannot be confirmed")
            row.status = "pending"

    def cancel_export(self, context: AuthContext, export_id: UUID) -> None:
        object_key: str | None = None
        with self._sessions.begin() as db:
            patient_id = self._patient_context(db, context)
            row = db.scalar(
                select(ExportOperation)
                .where(ExportOperation.id == export_id, ExportOperation.patient_id == patient_id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Export not found")
            row.status = "cancelled"
            row.capability_hash = None
            row.capability_expires_at = None
            object_key = row.object_key
        if object_key and self._storage is not None:
            versions = self._storage.list_object_versions(self._bucket, object_key)
            exact = [version for version in versions if version[0] == object_key]
            if not exact:
                exact = [(object_key, None)]
            for key, version_id in exact:
                self._storage.delete_object_version(self._bucket, key, version_id)

    def export_status(self, context: AuthContext, export_id: UUID) -> dict[str, object]:
        with self._sessions.begin() as db:
            patient_id = self._patient_context(db, context)
            row = db.scalar(
                select(ExportOperation)
                .where(
                    ExportOperation.id == export_id,
                    ExportOperation.patient_id == patient_id,
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Export not found")
            download_capability = None
            if row.status == "ready" and row.expires_at and row.expires_at > datetime.now(UTC):
                download_capability = secrets.token_urlsafe(32)
                row.capability_hash = _digest(download_capability)
                row.capability_expires_at = datetime.now(UTC) + timedelta(minutes=5)
                row.capability_used_at = None
            return {
                "export_id": row.id,
                "status": row.status,
                "categories": row.categories,
                "expires_at": row.expires_at,
                "download_capability": download_capability,
            }

    def list_exports(self, context: AuthContext) -> list[dict[str, object]]:
        with self._sessions.begin() as db:
            patient_id = self._patient_context(db, context)
            rows = db.scalars(
                select(ExportOperation)
                .where(ExportOperation.patient_id == patient_id)
                .order_by(ExportOperation.created_at.desc(), ExportOperation.id.desc())
                .limit(50)
            ).all()
            return [
                {
                    "export_id": row.id,
                    "status": row.status,
                    "categories": row.categories,
                    "expires_at": row.expires_at,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def download_export(self, capability: str) -> bytes:
        if self._storage is None or self._encryption_key is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        cap_hash = _digest(capability)
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.export_capability_hash', :hash, true)"),
                {"hash": cap_hash},
            )
            row = db.scalar(
                select(ExportOperation)
                .where(
                    ExportOperation.capability_hash == cap_hash,
                    ExportOperation.status == "ready",
                    ExportOperation.capability_used_at.is_(None),
                    ExportOperation.capability_expires_at > datetime.now(UTC),
                )
                .with_for_update()
            )
            if row is None or row.object_key is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            key = row.object_key
            wrapped_dek = row.wrapped_dek
            row.capability_used_at = datetime.now(UTC)
        try:
            if wrapped_dek is None or self._encryption_key is None:
                raise ValueError("Export key unavailable")
            wrap_nonce, wrapped = wrapped_dek[:12], wrapped_dek[12:]
            dek = AESGCM(self._encryption_key).decrypt(wrap_nonce, wrapped, None)
            content_length, _ = self._storage.head_object(self._bucket, key)
            _validate_export_size(content_length)
            limited_reader = getattr(self._storage, "read_object_limited", None)
            encrypted = (
                limited_reader(self._bucket, key, MAX_EXPORT_CIPHERTEXT_BYTES)
                if limited_reader is not None
                else self._storage.read_object(self._bucket, key)
            )
            _validate_export_size(len(encrypted))
            nonce, ciphertext = encrypted[:12], encrypted[12:]
            plaintext = AESGCM(dek).decrypt(nonce, ciphertext, None)
            _validate_export_size(len(encrypted), len(plaintext))
            return plaintext
        except Exception as error:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found") from error
