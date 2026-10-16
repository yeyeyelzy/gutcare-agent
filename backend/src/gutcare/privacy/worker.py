"""Lease-based F13 cleanup worker with durable object inventory replay."""

# ruff: noqa: E501 -- these SQL statements mirror the ordered cleanup contract.

import argparse
import base64
import hashlib
import json
import logging
import re
import secrets
import time
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from gutcare.config import get_settings
from gutcare.files.storage import S3ObjectStorage
from gutcare.privacy.models import DeletionOperation, DeletionStep, ExportOperation, ObjectInventory

logger = logging.getLogger("gutcare.privacy.worker")
LEASE = timedelta(minutes=5)
DELETE_PHASES = {
    "purge_derived": (
        "health.patient_notification",
        "health.notification_outbox",
        "analysis.advice_callback",
        "analysis.advice_feedback_event",
        "analysis.advice_feedback",
        "analysis.advice_evidence",
        "analysis.health_advice",
        "analysis.analysis_task_callback",
        "analysis.analysis_task_idempotency",
        "analysis.task_input_snapshot",
        "analysis.analysis_task",
    ),
    "purge_health": (
        "health.medical_candidate_decision_idempotency",
        "health.medical_candidate_decision",
        "health.medical_fact_conflict_member",
        "health.medical_fact_conflict",
        "health.confirmed_medical_fact",
        "health.medical_field_candidate",
        "health.medical_parse_request",
        "health.medical_document",
        "health.file_download_grant",
        "health.upload_session",
        "health.file_object",
        "health.diet_item",
        "health.diet_record",
        "health.stool_record",
        "health.symptom_status_event",
        "health.symptom_item",
        "health.symptom_record",
        "health.activity_record",
        "health.medication_checkin",
        "health.medication_schedule",
        "health.medication_source_ref",
        "health.medication_plan",
        "health.medication_idempotency",
        "health.record_idempotency",
        "health.notification_preference",
        "safety.alert_evidence",
        "safety.risk_alert",
        "integration.file_orphan_cleanup_job",
    ),
}
FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "password",
        "token",
        "callback",
        "idempotency",
        "prompt",
        "model_output",
        "source_locator",
        "object_key",
        "bucket_name",
    }
)
MAX_EXPORT_BYTES = 100 * 1024 * 1024


def scan_export_zip(payload: bytes) -> None:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        for entry in archive.infolist():
            if entry.filename.startswith("/") or ".." in entry.filename.split("/"):
                raise ValueError("Unsafe export entry path")
        data = json.loads(archive.read("data.json"))

    def scan_keys(value: object) -> None:
        if isinstance(value, dict):
            if any(str(key).lower() in FORBIDDEN_EXPORT_KEYS for key in value):
                raise ValueError("Forbidden export field")
            for nested in value.values():
                scan_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                scan_keys(nested)

    scan_keys(data)


class PrivacyWorker:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: S3ObjectStorage,
        bucket: str,
        encryption_key: bytes,
        raise_exceptions: bool = False,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._bucket = bucket
        self._encryption_key = encryption_key
        self._raise_exceptions = raise_exceptions

    def claim(self) -> UUID | None:
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            operation = db.scalar(
                select(DeletionOperation)
                .where(
                    or_(
                        (DeletionOperation.status.in_(("pending", "overdue")))
                        & or_(
                            DeletionOperation.lease_expires_at.is_(None),
                            DeletionOperation.lease_expires_at <= now,
                        ),
                        (DeletionOperation.status == "processing")
                        & (DeletionOperation.lease_expires_at <= now),
                    )
                )
                .order_by(DeletionOperation.requested_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if operation is None:
                return None
            operation.status = "overdue" if operation.due_at < now else "processing"
            operation.lease_owner = f"privacy-{secrets.token_hex(8)}"
            operation.lease_expires_at = now + LEASE
            operation.attempts += 1
            return operation.id

    def _step(self, db: Session, operation_id: UUID, code: str) -> bool:
        row = db.get(DeletionStep, (operation_id, code))
        return row is not None and row.status == "completed"

    def _step_exists(self, operation_id: UUID, code: str) -> bool:
        with self._sessions() as db:
            return self._step(db, operation_id, code)

    def _complete_step(self, db: Session, operation_id: UUID, code: str) -> None:
        now = datetime.now(UTC)
        row = db.get(DeletionStep, (operation_id, code))
        if row is None:
            row = DeletionStep(operation_id=operation_id, step_code=code)
            db.add(row)
        row.status = "completed"
        row.completed_at = now
        row.updated_at = now

    def _encrypt_key_digest(self, key: str) -> bytes:
        nonce = secrets.token_bytes(12)
        cipher = AESGCM(self._encryption_key).encrypt(
            nonce, hashlib.sha256(key.encode()).digest(), None
        )
        return nonce + cipher

    def _inventory(self, operation_id: UUID, patient_id: UUID) -> None:
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_id)}
            )
            operation = db.get(DeletionOperation, operation_id)
            if operation is None:
                return
            rows = (
                db.execute(
                    text("""
                    SELECT bucket_name, object_key, 'file_object' AS source_code
                    FROM health.file_object WHERE patient_id=:patient
                    UNION
                    SELECT bucket_name, object_key, 'upload_session' AS source_code
                    FROM health.upload_session WHERE patient_id=:patient
                    UNION
                    SELECT o.bucket_name, o.object_key, 'orphan' AS source_code
                    FROM integration.file_orphan_cleanup_job o
                    WHERE o.patient_id=:patient
                    UNION
                    SELECT :bucket, object_key, 'export' AS source_code
                    FROM privacy.export_operation WHERE patient_id=:patient AND object_key IS NOT NULL
                """),
                    {"patient": patient_id, "bucket": self._bucket},
                )
                .mappings()
                .all()
            )
            for row in rows:
                bucket_name, object_key, source_code = (
                    str(row["bucket_name"]),
                    str(row["object_key"]),
                    str(row["source_code"]),
                )
                versions = self._storage.list_object_versions(bucket_name, object_key)
                versions = [version for version in versions if version[0] == object_key]
                if not versions:
                    known = db.scalar(
                        select(ObjectInventory.id)
                        .where(
                            ObjectInventory.operation_id == operation_id,
                            ObjectInventory.bucket_name == bucket_name,
                            ObjectInventory.object_key == object_key,
                        )
                        .limit(1)
                    )
                    if known is not None:
                        continue
                    versions = [(object_key, None)]
                for version_key, version_id in versions:
                    exists = db.scalar(
                        select(ObjectInventory.id).where(
                            ObjectInventory.operation_id == operation_id,
                            ObjectInventory.bucket_name == bucket_name,
                            ObjectInventory.object_key == version_key,
                            ObjectInventory.version_id.is_not_distinct_from(version_id),
                        )
                    )
                    if exists is None:
                        db.add(
                            ObjectInventory(
                                operation_id=operation_id,
                                bucket_name=bucket_name,
                                object_key=version_key,
                                version_id=version_id,
                                source_code=source_code,
                            )
                        )

    def _delete_inventory(self, operation_id: UUID) -> None:
        with self._sessions() as db:
            items = db.scalars(
                select(ObjectInventory).where(
                    ObjectInventory.operation_id == operation_id,
                    ObjectInventory.status != "deleted",
                )
            ).all()
        for item in items:
            key = item.object_key
            if key is None:
                continue
            try:
                self._storage.delete_object_version(item.bucket_name, key, item.version_id)
                with self._sessions.begin() as db:
                    stored = db.get(ObjectInventory, item.id)
                    if stored is not None:
                        stored.status = "deleted"
                        stored.deleted_at = datetime.now(UTC)
                        stored.key_digest_ciphertext = self._encrypt_key_digest(key)
                        stored.object_key = None
            except Exception:
                with self._sessions.begin() as db:
                    stored = db.get(ObjectInventory, item.id)
                    if stored is not None:
                        stored.status = "failed"
                        stored.attempts += 1
                        stored.last_error_code = "OBJECT_DELETE_FAILED"
                raise

    def _assert_inventory_deleted(self, operation_id: UUID) -> None:
        with self._sessions() as db:
            pending = db.scalar(
                select(ObjectInventory.id)
                .where(
                    ObjectInventory.operation_id == operation_id,
                    ObjectInventory.status != "deleted",
                )
                .limit(1)
            )
        if pending is not None:
            raise RuntimeError("Object inventory is not fully deleted")

    def process_one(self) -> bool:
        operation_id = self.claim()
        if operation_id is None:
            return False
        try:
            with self._sessions.begin() as db:
                operation = db.get(DeletionOperation, operation_id)
                if operation is None or operation.patient_id is None:
                    return True
                patient_id = operation.patient_id
            # Re-enumerate on every lease claim so restored or late-arriving object
            # versions are added to the durable inventory before destructive phases.
            self._inventory(operation_id, patient_id)
            if not self._step_exists(operation_id, "freeze"):
                with self._sessions.begin() as db:
                    self._complete_step(db, operation_id, "freeze")
            if not self._step_exists(operation_id, "inventory"):
                with self._sessions.begin() as db:
                    self._complete_step(db, operation_id, "inventory")
            if not self._step_exists(operation_id, "revoke_capabilities"):
                with self._sessions.begin() as db:
                    db.execute(
                        text("SELECT set_config('app.patient_id', :id, true)"),
                        {"id": str(patient_id)},
                    )
                    db.execute(
                        text(
                            "UPDATE privacy.export_operation SET status='cancelled', capability_hash=NULL, wrapped_dek=NULL WHERE patient_id=:patient AND status IN ('preview','pending','processing','ready')"
                        ),
                        {"patient": patient_id},
                    )
                    db.execute(
                        text(
                            "UPDATE health.file_download_grant SET expires_at=now() WHERE patient_id=:patient"
                        ),
                        {"patient": patient_id},
                    )
                    db.execute(
                        text(
                            "UPDATE health.upload_session SET status='expired', expires_at=now() WHERE patient_id=:patient"
                        ),
                        {"patient": patient_id},
                    )
                    self._complete_step(db, operation_id, "revoke_capabilities")
            # Always drain inventory after each lease claim. The ledger records that
            # an earlier pass completed, but newly discovered object versions still
            # require deletion before any patient rows or tombstones can be finalized.
            self._delete_inventory(operation_id)
            self._assert_inventory_deleted(operation_id)
            if not self._step_exists(operation_id, "delete_objects"):
                with self._sessions.begin() as db:
                    self._complete_step(db, operation_id, "delete_objects")
            for phase, tables in DELETE_PHASES.items():
                if self._step_exists(operation_id, phase):
                    continue
                with self._sessions.begin() as db:
                    db.execute(
                        text("SELECT set_config('app.patient_id', :id, true)"),
                        {"id": str(patient_id)},
                    )
                    for table in tables:
                        db.execute(
                            text(f"DELETE FROM {table} WHERE patient_id=:patient"),
                            {"patient": patient_id},
                        )
                    self._complete_step(db, operation_id, phase)
            with self._sessions.begin() as db:
                operation = db.get(DeletionOperation, operation_id)
                if operation is None:
                    return True
                self._assert_inventory_deleted(operation_id)
                if not self._step(db, operation_id, "purge_identity"):
                    db.execute(
                        text("SELECT set_config('app.patient_id', :id, true)"),
                        {"id": str(patient_id)},
                    )
                    user_id = db.execute(
                        text("SELECT user_id FROM health.patient_profile WHERE id=:id"),
                        {"id": patient_id},
                    ).scalar_one_or_none()
                    if user_id is not None:
                        db.execute(
                            text("DELETE FROM health.patient_consent WHERE patient_id=:patient"),
                            {"patient": patient_id},
                        )
                        db.execute(
                            text("DELETE FROM health.patient_profile WHERE id=:id"),
                            {"id": patient_id},
                        )
                        db.execute(
                            text("DELETE FROM iam.user_account WHERE id=:id"), {"id": user_id}
                        )
                    operation.patient_id = None
                    self._complete_step(db, operation_id, "purge_identity")
                self._complete_step(db, operation_id, "finalize")
                operation.status = "completed"
                operation.completed_at = datetime.now(UTC)
                operation.lease_owner = None
                operation.lease_expires_at = None
                operation.last_error_code = None
                db.execute(
                    text(
                        "INSERT INTO privacy.security_audit (operation_hash,event_code,expires_at) VALUES (:hash,'DELETION_COMPLETED',:expiry)"
                    ),
                    {
                        "hash": operation.account_hash,
                        "expiry": datetime.now(UTC) + timedelta(days=180),
                    },
                )
            return True
        except Exception:
            if self._raise_exceptions:
                raise
            with self._sessions.begin() as db:
                operation = db.get(DeletionOperation, operation_id)
                if operation is not None:
                    is_dead_letter = operation.attempts >= 8
                    operation.status = (
                        "dead_letter"
                        if is_dead_letter
                        else ("overdue" if operation.due_at < datetime.now(UTC) else "pending")
                    )
                    operation.last_error_code = "PRIVACY_CLEANUP_FAILED"
                    operation.lease_owner = None
                    retry_delay = min(3600, 2 ** min(operation.attempts, 12))
                    operation.lease_expires_at = (
                        None
                        if is_dead_letter
                        else datetime.now(UTC) + timedelta(seconds=retry_delay)
                    )
            return True

    @staticmethod
    def _json_default(value: object) -> str:
        if isinstance(value, (datetime, UUID)):
            return value.isoformat() if isinstance(value, datetime) else str(value)
        return str(value)

    def _export_payload(
        self, db: Session, patient_id: UUID, categories: list[str]
    ) -> tuple[dict[str, object], list[tuple[str, bytes]]]:
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_id)})
        query_map: dict[str, list[tuple[str, str]]] = {
            "profile": [
                (
                    "profile",
                    "SELECT nickname,birth_year,timezone,profile_version,created_at,updated_at FROM health.patient_profile WHERE id=:patient",
                )
            ],
            "consents": [
                (
                    "consents",
                    "SELECT consent_type,document_version,granted,decided_at,revoked_at FROM health.patient_consent WHERE patient_id=:patient ORDER BY decided_at,id",
                )
            ],
            "medical_documents": [
                (
                    "medical_documents",
                    "SELECT document_type,hospital_name,document_date,notes,processing_mode,parse_status,record_version,created_at,updated_at FROM health.medical_document WHERE patient_id=:patient ORDER BY created_at,id",
                )
            ],
            "files": [
                (
                    "files",
                    "SELECT id,original_name,content_type,size_bytes,sensitivity,created_at FROM health.file_object WHERE patient_id=:patient AND storage_status='available' AND scan_status='clean' ORDER BY created_at,id",
                )
            ],
            "diet": [
                (
                    "diet_records",
                    "SELECT id,occurred_at,meal_type,text_description,portion_note,payload,source_type,confirmation_status,record_version,created_at,updated_at FROM health.diet_record WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY occurred_at,id",
                ),
                (
                    "diet_items",
                    "SELECT diet_record_id,name,category_code,amount_text,source_type,confirmed_by_patient FROM health.diet_item WHERE patient_id=:patient ORDER BY diet_record_id,id",
                ),
            ],
            "stool": [
                (
                    "stool_records",
                    "SELECT id,occurred_at,bristol_type,color_code,blood_reported,payload,source_type,confirmation_status,record_version,created_at,updated_at FROM health.stool_record WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY occurred_at,id",
                )
            ],
            "symptoms": [
                (
                    "symptom_records",
                    "SELECT id,occurred_at,duration_minutes,notes,symptom_status,payload,source_type,record_version,created_at,updated_at FROM health.symptom_record WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY occurred_at,id",
                ),
                (
                    "symptom_items",
                    "SELECT symptom_record_id,symptom_code,other_description,severity,body_location,patient_confirmed FROM health.symptom_item WHERE patient_id=:patient ORDER BY symptom_record_id,id",
                ),
            ],
            "medication": [
                (
                    "medication_plans",
                    "SELECT medication_name,dosage_text,route_code,start_date,end_date,source_type,confirmation_status,plan_status,record_version,created_at,updated_at FROM health.medication_plan WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY created_at,id",
                ),
                (
                    "medication_schedules",
                    "SELECT plan_id,local_time,timezone,rrule,valid_from,valid_to,enabled,record_version FROM health.medication_schedule WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY plan_id,local_time,id",
                ),
                (
                    "medication_checkins",
                    "SELECT schedule_id,local_date,scheduled_for,status,record_version,taken_at,note,created_at,updated_at FROM health.medication_checkin WHERE patient_id=:patient ORDER BY scheduled_for,id",
                ),
            ],
            "activity": [
                (
                    "activity_records",
                    "SELECT activity_type,description,intensity,subjective_feeling,duration_minutes,occurred_at,record_version,created_at,updated_at FROM health.activity_record WHERE patient_id=:patient AND deleted_at IS NULL ORDER BY occurred_at,id",
                )
            ],
            "analysis": [
                (
                    "analysis_tasks",
                    "SELECT analysis_type,status,requested_from,requested_to,attempt,created_at,updated_at FROM analysis.analysis_task WHERE patient_id=:patient ORDER BY created_at,id",
                )
            ],
            "advice": [
                (
                    "advice",
                    "SELECT category,priority,title,body,uncertainty,applicability,safety_boundary,version,status,basis_updated,basis_updated_at,basis_update_reason,created_at FROM analysis.health_advice WHERE patient_id=:patient ORDER BY created_at,id",
                )
            ],
            "alerts": [
                (
                    "risk_alerts",
                    "SELECT severity,message,recommended_action,status,triggered_at,read_at,reevaluated_at FROM safety.risk_alert WHERE patient_id=:patient ORDER BY triggered_at,id",
                )
            ],
            "notifications": [
                (
                    "notifications",
                    "SELECT event_type,category,priority,occurred_at,read_at,created_at FROM health.patient_notification WHERE patient_id=:patient ORDER BY occurred_at,id",
                )
            ],
        }
        datasets: dict[str, object] = {}
        unavailable_file_ids: list[str] = []
        attachments: list[tuple[str, bytes]] = []
        attachment_bytes = 0
        for category in categories:
            for dataset_name, sql in query_map[category]:
                rows = db.execute(text(sql), {"patient": patient_id}).mappings().all()
                datasets[dataset_name] = [dict(row) for row in rows]
                if category == "files":
                    file_rows = (
                        db.execute(
                            text(
                                "SELECT id,bucket_name,object_key,original_name,size_bytes FROM health.file_object WHERE patient_id=:patient AND storage_status='available' AND scan_status='clean' ORDER BY created_at,id"
                            ),
                            {"patient": patient_id},
                        )
                        .mappings()
                        .all()
                    )
                    for item in file_rows:
                        raw_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(item["original_name"]))[:128]
                        try:
                            actual_size, _content_type = self._storage.head_object(
                                str(item["bucket_name"]), str(item["object_key"])
                            )
                            remaining = MAX_EXPORT_BYTES - attachment_bytes
                            if actual_size < 0 or actual_size > remaining:
                                raise ValueError("Export attachment limit exceeded")
                            limited_reader = getattr(self._storage, "read_object_limited", None)
                            contents = (
                                limited_reader(
                                    str(item["bucket_name"]), str(item["object_key"]), remaining
                                )
                                if limited_reader is not None
                                else self._storage.read_object(
                                    str(item["bucket_name"]), str(item["object_key"])
                                )
                            )
                            if len(contents) > remaining or len(contents) != actual_size:
                                raise ValueError("Export attachment limit exceeded")
                            attachment_bytes += len(contents)
                            attachments.append((f"files/{item['id']}_{raw_name}", contents))
                        except Exception:
                            # An unreadable source is omitted from this archive and surfaced in the manifest.
                            unavailable_file_ids.append(str(item["id"]))
        if unavailable_file_ids:
            datasets["unavailable_file_ids"] = unavailable_file_ids
        return datasets, attachments

    def process_export_one(self) -> bool:
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            operation = db.scalar(
                select(ExportOperation)
                .where(
                    (ExportOperation.status == "pending")
                    | (
                        (ExportOperation.status == "processing")
                        & (ExportOperation.lease_expires_at < now)
                    )
                )
                .order_by(ExportOperation.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if operation is None:
                return False
            operation.status = "processing"
            operation.lease_owner = f"privacy-export-{secrets.token_hex(8)}"
            operation.lease_expires_at = now + LEASE
            operation.attempts += 1
            object_key = f"exports/{operation.id}.zip.enc"
            operation.object_key = object_key
            export_id = operation.id
            lease_owner = operation.lease_owner
            patient_id = operation.patient_id
            categories = list(operation.categories)
        try:
            with self._sessions() as db:
                datasets, attachments = self._export_payload(db, patient_id, categories)
            zip_buffer = BytesIO()
            manifest_files: list[dict[str, object]] = []
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                data_bytes = json.dumps(
                    {"schema_version": "1.0", "datasets": datasets},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=self._json_default,
                ).encode()
                if len(data_bytes) > MAX_EXPORT_BYTES:
                    raise ValueError("Export JSON exceeds the configured size bound")
                uncompressed_total = len(data_bytes)
                archive.writestr("data.json", data_bytes)
                if zip_buffer.tell() > MAX_EXPORT_BYTES:
                    raise ValueError("Export archive exceeds the configured size bound")
                manifest_files.append(
                    {
                        "name": "data.json",
                        "sha256": hashlib.sha256(data_bytes).hexdigest(),
                        "size_bytes": len(data_bytes),
                    }
                )
                for name, contents in attachments:
                    uncompressed_total += len(contents)
                    if uncompressed_total > MAX_EXPORT_BYTES:
                        raise ValueError("Export plaintext exceeds the configured size bound")
                    archive.writestr(name, contents)
                    if zip_buffer.tell() > MAX_EXPORT_BYTES:
                        raise ValueError("Export archive exceeds the configured size bound")
                    manifest_files.append(
                        {
                            "name": name,
                            "sha256": hashlib.sha256(contents).hexdigest(),
                            "size_bytes": len(contents),
                        }
                    )
                manifest = json.dumps(
                    {
                        "schema_version": "1.0",
                        "exported_at": datetime.now(UTC).isoformat(),
                        "categories": categories,
                        "files": manifest_files,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                archive.writestr("manifest.json", manifest)
                if uncompressed_total + len(manifest) > MAX_EXPORT_BYTES:
                    raise ValueError("Export plaintext exceeds the configured size bound")
                if zip_buffer.tell() > MAX_EXPORT_BYTES:
                    raise ValueError("Export archive exceeds the configured size bound")
            zip_bytes = zip_buffer.getvalue()
            if len(zip_bytes) > MAX_EXPORT_BYTES:
                raise ValueError("Export archive exceeds the configured size bound")
            scan_export_zip(zip_bytes)
            dek = AESGCM.generate_key(bit_length=256)
            nonce = secrets.token_bytes(12)
            encrypted_zip = nonce + AESGCM(dek).encrypt(nonce, zip_bytes, None)
            wrap_nonce = secrets.token_bytes(12)
            wrapped_dek = wrap_nonce + AESGCM(self._encryption_key).encrypt(wrap_nonce, dek, None)
            self._storage.put_object(
                self._bucket, object_key, encrypted_zip, "application/octet-stream"
            )
            with self._sessions.begin() as db:
                row = db.get(ExportOperation, export_id)
                if row is None or row.status != "processing" or row.lease_owner != lease_owner:
                    self._delete_export_versions(object_key)
                    if (
                        row is not None
                        and row.status == "cancelled"
                        and row.lease_owner == lease_owner
                    ):
                        row.lease_owner = None
                        row.lease_expires_at = None
                    return True
                row.status = "ready"
                row.object_key = object_key
                row.wrapped_dek = wrapped_dek
                row.completed_at = datetime.now(UTC)
                row.expires_at = datetime.now(UTC) + timedelta(hours=24)
                row.lease_owner = None
                row.lease_expires_at = None
                row.last_error_code = None
            return True
        except Exception:
            if self._raise_exceptions:
                raise
            with self._sessions.begin() as db:
                row = db.get(ExportOperation, export_id)
                if (
                    row is not None
                    and row.status == "processing"
                    and row.lease_owner == lease_owner
                ):
                    row.status = "failed" if row.attempts >= 3 else "pending"
                    row.last_error_code = "EXPORT_BUILD_FAILED"
                    row.lease_owner = None
                    row.lease_expires_at = None
            return True

    def _delete_export_versions(self, object_key: str) -> None:
        versions = self._storage.list_object_versions(self._bucket, object_key)
        exact = [version for version in versions if version[0] == object_key]
        for key, version_id in exact:
            self._storage.delete_object_version(self._bucket, key, version_id)

    def cleanup_expired_exports(self) -> int:
        now = datetime.now(UTC)
        with self._sessions() as db:
            expired = db.scalars(
                select(ExportOperation)
                .where(
                    ((ExportOperation.status == "ready") & (ExportOperation.expires_at <= now))
                    | (
                        (ExportOperation.status == "cancelled")
                        & ExportOperation.object_key.is_not(None)
                        & (
                            ExportOperation.lease_expires_at.is_(None)
                            | (ExportOperation.lease_expires_at <= now)
                        )
                    ),
                )
                .limit(50)
            ).all()
            targets = [(row.id, row.object_key) for row in expired]
        removed = 0
        for export_id, object_key in targets:
            if object_key:
                self._delete_export_versions(object_key)
                remaining = [
                    version
                    for version in self._storage.list_object_versions(self._bucket, object_key)
                    if version[0] == object_key
                ]
                if remaining:
                    continue
            with self._sessions.begin() as db:
                row = db.get(ExportOperation, export_id)
                if row is not None and (
                    row.status == "cancelled"
                    or (
                        row.status == "ready"
                        and row.expires_at is not None
                        and row.expires_at <= now
                    )
                ):
                    if row.status == "ready":
                        row.status = "expired"
                        removed += 1
                    row.capability_hash = None
                    row.capability_expires_at = None
                    row.object_key = None
                    row.wrapped_dek = None
        with self._sessions.begin() as db:
            db.execute(
                text("DELETE FROM privacy.security_audit WHERE expires_at <= :now"), {"now": now}
            )
        return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="GutCare privacy lifecycle worker")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="one-shot recovery replay of pending/expired deletion operations before readiness",
    )
    args = parser.parse_args()
    settings = get_settings()
    required = (
        settings.privacy_worker_database_url,
        settings.object_storage_endpoint,
        settings.object_storage_access_key,
        settings.object_storage_secret_key,
        settings.export_kek,
    )
    if any(value is None for value in required):
        raise RuntimeError("Privacy worker database, storage and encryption settings are required")
    assert settings.privacy_worker_database_url is not None
    assert settings.object_storage_endpoint is not None
    assert settings.object_storage_access_key is not None
    assert settings.object_storage_secret_key is not None
    assert settings.export_kek is not None
    url = str(settings.privacy_worker_database_url)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    padded = settings.export_kek + "=" * (-len(settings.export_kek) % 4)
    encryption_key = base64.urlsafe_b64decode(padded.encode())
    if len(encryption_key) != 32:
        raise RuntimeError("Privacy encryption key must be 32 bytes")
    engine = create_engine(url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    worker = PrivacyWorker(
        sessions,
        S3ObjectStorage(
            str(settings.object_storage_endpoint),
            settings.object_storage_access_key,
            settings.object_storage_secret_key,
        ),
        settings.object_storage_bucket,
        encryption_key,
    )
    try:
        if args.replay:
            # Drain all deletions that were pending in the restored database. Each operation
            # retains its durable phase ledger and object version inventory, so reruns are safe.
            while worker.process_one():
                pass
            with sessions() as db:
                blockers = (
                    db.execute(
                        text(
                            "SELECT id::text AS operation_id,status,last_error_code,attempts FROM privacy.deletion_operation WHERE status IN ('pending','overdue','processing','dead_letter') ORDER BY requested_at"
                        )
                    )
                    .mappings()
                    .all()
                )
            remaining = len(blockers)
            if remaining:
                safe_summary = ", ".join(
                    f"operation_id={row['operation_id']} status={row['status']} "
                    f"error_code={row['last_error_code']} attempts={row['attempts']}"
                    for row in blockers
                )
                raise RuntimeError(f"Privacy replay left unfinished operations: {safe_summary}")
            logger.info("Privacy deletion replay completed; readiness may be enabled")
            return
        while True:
            try:
                worked = worker.process_one()
                if not worked:
                    worker.process_export_one()
                worker.cleanup_expired_exports()
            except Exception:
                logger.exception("Privacy worker cycle failed")
            time.sleep(3)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
