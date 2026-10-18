"""Application services for upload, medical archive and private download flows."""
# ruff: noqa: E501

from __future__ import annotations

import hmac
import json
import logging
import secrets
import unicodedata
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import PurePath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, desc, func, or_, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.models import PatientConsent, PatientProfile
from gutcare.auth.service import AuthContext
from gutcare.files.models import (
    AGENT_MEDICAL_FIELD_TYPE_PAIRS,
    ConfirmedMedicalFact,
    FileDeletionJob,
    FileDownloadGrant,
    FileObject,
    FileOrphanCleanupJob,
    MedicalCandidateDecision,
    MedicalCandidateDecisionIdempotency,
    MedicalDocument,
    MedicalFactConflict,
    MedicalFactConflictMember,
    MedicalFieldCandidate,
    MedicalParseRequest,
    UploadSession,
)
from gutcare.files.policy import allowed_upload, validate_file
from gutcare.files.scanner import MalwareScanner, ScannerUnavailable
from gutcare.files.storage import ObjectStorage
from gutcare.medication.models import MedicationSourceRef
from gutcare.shared.errors import Problem

logger = logging.getLogger("gutcare.files")
UPLOAD_TTL = timedelta(minutes=15)
DOWNLOAD_TTL = timedelta(minutes=5)
DELETE_GRACE = timedelta(days=7)


def _normal_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _canonical_decimal(value: Any) -> str | None:
    """Return a context-independent, bounded canonical form for finite decimals."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    parts = number.as_tuple()
    digits = list(parts.digits)
    if not any(digits):
        return "0"
    while digits and digits[0] == 0:
        digits.pop(0)
    exponent = int(parts.exponent)
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    sign = "-" if parts.sign else ""
    return f"{sign}{''.join(map(str, digits))}e{exponent}"


@dataclass(frozen=True, slots=True)
class UploadSessionData:
    upload_id: UUID
    upload_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class FileObjectData:
    id: UUID
    storage_status: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class MedicalDocumentData:
    id: UUID
    file_object_id: UUID
    document_type: str
    hospital_name: str | None
    document_date: date | None
    notes: str | None
    processing_mode: str
    parse_status: str
    parse_outcome: str | None
    parse_reason_code: str | None
    record_version: int
    created_at: datetime
    updated_at: datetime
    file_status: str
    original_name: str


@dataclass(frozen=True, slots=True)
class DocumentPageData:
    items: list[MedicalDocumentData]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class DownloadGrantData:
    download_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MedicalCandidateData:
    id: UUID
    field_code: str
    value_type: str
    value: Any
    unit: str | None
    confidence: float | None
    uncertainty: str | None
    source_locator: dict[str, Any] | None
    excerpt: str | None
    review_status: str
    record_version: int
    chosen_value: Any


def capability_digest(token: str) -> str:
    return sha256(token.encode("ascii")).hexdigest()


def _safe_filename(value: str) -> str:
    name = PurePath(value.replace("\\", "/")).name
    if not name or name in {".", ".."} or len(name) > 255:
        raise Problem(422, "VALIDATION_ERROR", "Invalid file name")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise Problem(422, "VALIDATION_ERROR", "Invalid file name")
    return name


def _request_hash(purpose: str, filename: str, content_type: str, size_bytes: int) -> str:
    encoded = json.dumps(
        {
            "purpose": purpose,
            "file_name": filename,
            "content_type": content_type.lower(),
            "size_bytes": size_bytes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _document_data(document: MedicalDocument, file_object: FileObject) -> MedicalDocumentData:
    return MedicalDocumentData(
        id=document.id,
        file_object_id=document.file_object_id,
        document_type=document.document_type,
        hospital_name=document.hospital_name,
        document_date=document.document_date,
        notes=document.notes,
        processing_mode=document.processing_mode,
        parse_status=document.parse_status,
        parse_outcome=document.parse_outcome,
        parse_reason_code=document.parse_reason_code,
        record_version=document.record_version,
        created_at=document.created_at,
        updated_at=document.updated_at,
        file_status=file_object.storage_status,
        original_name=file_object.original_name,
    )


class FileService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        storage: ObjectStorage,
        scanner: MalwareScanner,
        public_base_url: str,
        bucket_name: str,
        capability_secret: str,
        worker_sessions: sessionmaker[Session] | None = None,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._scanner = scanner
        self._public_base_url = public_base_url.rstrip("/")
        self._bucket = bucket_name
        self._worker_sessions = worker_sessions
        if len(capability_secret) < 32:
            raise ValueError("file capability secret must contain at least 32 characters")
        self._capability_secret = capability_secret.encode("utf-8")

    def _upload_capability(self, session_id: UUID, request_hash: str) -> str:
        message = f"upload:{session_id}:{request_hash}".encode("ascii")
        digest = hmac.new(self._capability_secret, message, "sha256").digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def validate_medical_candidate(item: dict[str, Any]) -> None:
        schema = AGENT_MEDICAL_FIELD_TYPE_PAIRS
        required = {
            "field_code",
            "value_type",
            "value",
            "unit",
            "confidence",
            "uncertainty",
            "source_locator",
            "excerpt",
        }
        if (
            set(item) != required
            or item["field_code"] not in schema
            or item["value_type"] != schema[item["field_code"]]
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate field schema is invalid")
        value, kind = item["value"], item["value_type"]
        if kind == "date":
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError) as exc:
                raise Problem(422, "VALIDATION_ERROR", "Candidate date must be ISO date") from exc
        elif kind == "string" and (not isinstance(value, str) or not value or len(value) > 2000):
            raise Problem(422, "VALIDATION_ERROR", "Candidate text value is invalid")
        elif kind == "object" and (not isinstance(value, dict) or not value):
            raise Problem(422, "VALIDATION_ERROR", "Candidate object value is invalid")
        if item["field_code"] == "test_result":
            if (
                set(value) - {"result", "unit", "reference_range", "flag", "sampled_on"}
                or "result" not in value
            ):
                raise Problem(422, "VALIDATION_ERROR", "Test result structure is invalid")
            if type(value["result"]) not in (str, int, float) or (
                isinstance(value["result"], str) and len(value["result"]) > 200
            ):
                raise Problem(422, "VALIDATION_ERROR", "Test result value is invalid")
            if isinstance(value["result"], (int, float)) or (
                isinstance(value["result"], str)
                and value["result"].strip().casefold()
                in {
                    "nan",
                    "+nan",
                    "-nan",
                    "inf",
                    "+inf",
                    "-inf",
                    "infinity",
                    "+infinity",
                    "-infinity",
                }
            ):
                try:
                    if not Decimal(str(value["result"])).is_finite():
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise Problem(422, "VALIDATION_ERROR", "Test result must be finite") from exc
            allowed_units = {
                None,
                "",
                "mg/L",
                "mg/dL",
                "g/L",
                "mmol/L",
                "umol/L",
                "10^9/L",
                "10^12/L",
                "%",
                "U/L",
                "IU/L",
                "mL",
                "L",
                "pg/mL",
                "ng/mL",
            }
            if value.get("unit") not in (None, "") and _normal_text(value["unit"]) not in {
                _normal_text(unit) for unit in allowed_units if unit
            }:
                raise Problem(422, "VALIDATION_ERROR", "Test result unit is unsupported")
            if _normal_text(item["unit"] or "") != _normal_text(value.get("unit") or ""):
                raise Problem(422, "VALIDATION_ERROR", "Test result unit does not match")
            if value.get("sampled_on") is not None:
                try:
                    date.fromisoformat(value["sampled_on"])
                except (ValueError, TypeError) as exc:
                    raise Problem(422, "VALIDATION_ERROR", "Sample date must be ISO date") from exc
        elif item["field_code"] == "medication_dose":
            if (
                set(value) != {"amount", "unit"}
                or type(value["amount"]) not in (int, float)
                or value["amount"] <= 0
                or value["unit"] not in {"mg", "mcg", "g", "mL", "tablet", "capsule", "unit"}
            ):
                raise Problem(422, "VALIDATION_ERROR", "Medication dose structure is invalid")
            if item["unit"] != value["unit"]:
                raise Problem(422, "VALIDATION_ERROR", "Medication dose unit does not match")
        elif kind in {"string", "date", "diagnosis"} and item["unit"] is not None:
            raise Problem(422, "VALIDATION_ERROR", "Unit is not valid for this field")
        elif kind == "diagnosis" and (
            not isinstance(value, dict)
            or set(value) != {"text", "certainty"}
            or not isinstance(value["text"], str)
            or value["certainty"] not in {"explicit", "suspected", "rule_out", "history"}
        ):
            raise Problem(422, "VALIDATION_ERROR", "Diagnosis candidate is invalid")
        confidence = item["confidence"]
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate confidence is invalid")
        locator = item["source_locator"]
        if (
            not isinstance(locator, dict)
            or not locator
            or set(locator) - {"page", "char_start", "char_end", "bbox"}
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate locator is invalid")
        if "page" in locator and (type(locator["page"]) is not int or locator["page"] < 1):
            raise Problem(422, "VALIDATION_ERROR", "Candidate page is invalid")
        if ("char_start" in locator) != ("char_end" in locator):
            raise Problem(422, "VALIDATION_ERROR", "Candidate range is invalid")
        if "char_start" in locator and (
            type(locator["char_start"]) is not int
            or type(locator["char_end"]) is not int
            or locator["char_start"] < 0
            or locator["char_end"] <= locator["char_start"]
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate range is invalid")
        if "bbox" in locator and (
            not isinstance(locator["bbox"], list)
            or len(locator["bbox"]) != 4
            or any(type(x) not in (int, float) or not 0 <= x <= 1 for x in locator["bbox"])
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate bounding box is invalid")
        if "bbox" in locator and (
            locator["bbox"][2] <= 0
            or locator["bbox"][3] <= 0
            or locator["bbox"][0] + locator["bbox"][2] > 1
            or locator["bbox"][1] + locator["bbox"][3] > 1
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate bounding box exceeds page bounds")
        if (
            not any(k in locator for k in ("page", "char_start", "bbox"))
            or not isinstance(item["excerpt"], str)
            or not item["excerpt"]
            or len(item["excerpt"]) > 500
        ):
            raise Problem(422, "VALIDATION_ERROR", "Candidate evidence is invalid")

    def submit_medical_candidates(
        self,
        request_id: UUID,
        callback_id: UUID,
        candidates: list[dict[str, Any]],
        *,
        parse_outcome: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        # Older internal callers may omit the additive outcome only for non-empty
        # candidate batches. Empty results must carry an explicit controlled outcome.
        outcome = parse_outcome or ("extracted" if candidates else None)
        reason_groups = {
            "no_supported_facts": {"no_supported_fields", "unsupported_content"},
            "insufficient_quality": {
                "low_quality_scan",
                "illegible_content",
                "incomplete_document",
            },
        }
        if outcome == "extracted":
            valid_shape = bool(candidates) and reason_code is None
        elif outcome in reason_groups:
            valid_shape = not candidates and reason_code in reason_groups[outcome]
        else:
            valid_shape = False
        if not valid_shape:
            raise Problem(422, "VALIDATION_ERROR", "Parse outcome and candidate count are invalid")
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.medical_parse_request_id', :value, true)"),
                {"value": str(request_id)},
            )
            probe = db.scalar(
                select(MedicalParseRequest).where(MedicalParseRequest.id == request_id)
            )
            if probe is None:
                raise Problem(409, "PARSE_REQUEST_STALE", "Parse request is no longer active")
            self._lock_patient_consent_fence(db, probe.patient_id)
            self._require_medical_analysis_consents(db, probe.patient_id)
            req = db.scalar(
                select(MedicalParseRequest)
                .where(MedicalParseRequest.id == request_id)
                .with_for_update()
            )
            if req is None:
                raise Problem(409, "PARSE_REQUEST_STALE", "Parse request is no longer active")
            for item in candidates:
                self.validate_medical_candidate(item)
            callback_hash = sha256(
                json.dumps(
                    {
                        "parse_outcome": outcome,
                        "reason_code": reason_code,
                        "candidates": candidates,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if (
                req is not None
                and req.callback_id == callback_id
                and req.status in {"needs_confirmation", "succeeded"}
            ):
                if req.callback_hash != callback_hash:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Callback ID was reused")
                return
            if req is None or req.status not in {"processing", "pending"}:
                raise Problem(409, "PARSE_REQUEST_STALE", "Parse request is no longer active")
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"),
                {"value": str(req.patient_id)},
            )
            doc = db.scalar(
                select(MedicalDocument)
                .where(
                    MedicalDocument.id == req.document_id,
                    MedicalDocument.patient_id == req.patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
            file_object = db.scalar(
                select(FileObject).where(
                    FileObject.id == req.file_object_id,
                    FileObject.patient_id == req.patient_id,
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if (
                doc is None
                or file_object is None
                or doc.record_version != req.record_version
                or doc.file_object_id != req.file_object_id
            ):
                req.status = "invalidated"
                raise Problem(
                    409, "PARSE_REQUEST_STALE", "Source document changed or is unavailable"
                )
            req.callback_id = callback_id
            req.callback_hash = callback_hash
            for item in candidates:
                db.add(
                    MedicalFieldCandidate(
                        patient_id=req.patient_id,
                        request_id=req.id,
                        field_code=item["field_code"],
                        value_type=item["value_type"],
                        value=item["value"],
                        unit=item["unit"],
                        confidence=item["confidence"],
                        uncertainty=item["uncertainty"],
                        source_locator=item["source_locator"],
                        excerpt=item["excerpt"],
                    )
                )
            req.status = "needs_confirmation" if outcome == "extracted" else "succeeded"
            req.finished_at = datetime.now(UTC)
            req.parse_outcome = outcome
            req.parse_reason_code = reason_code
            doc.parse_outcome = outcome
            doc.parse_reason_code = reason_code
            # Keep the existing document lifecycle state. The additive outcome
            # distinguishes zero-candidate success from confirmation work.
            doc.parse_status = "needs_confirmation"

    def get_medical_parse_inputs(self, request_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.medical_parse_request_id', :value, true)"),
                {"value": str(request_id)},
            )
            probe = db.scalar(
                select(MedicalParseRequest).where(MedicalParseRequest.id == request_id)
            )
            if probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            self._lock_patient_consent_fence(db, probe.patient_id)
            self._require_medical_analysis_consents(db, probe.patient_id)
            req = db.scalar(
                select(MedicalParseRequest)
                .where(MedicalParseRequest.id == request_id)
                .with_for_update(read=True)
            )
            if req is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if req.status != "processing":
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            doc = db.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.id == req.document_id,
                    MedicalDocument.patient_id == req.patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
            )
            file_object = db.scalar(
                select(FileObject).where(
                    FileObject.id == req.file_object_id,
                    FileObject.patient_id == req.patient_id,
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if (
                doc is None
                or file_object is None
                or doc.record_version != req.record_version
                or doc.file_object_id != req.file_object_id
            ):
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            result = {
                "request_id": req.id,
                "document_id": doc.id,
                "document_version": doc.record_version,
                "document_type": doc.document_type,
                "document_date": doc.document_date,
                "content_type": file_object.content_type,
                "file_name": file_object.original_name,
                "content": self._storage.read_object(
                    file_object.bucket_name, file_object.object_key
                ),
            }
            return result

    def fail_medical_parse_request(
        self, request_id: UUID, callback_id: UUID, error_code: str
    ) -> None:
        if not error_code or len(error_code) > 64 or not error_code.replace("_", "").isalnum():
            raise Problem(422, "VALIDATION_ERROR", "Parse failure code is invalid")
        callback_hash = sha256(error_code.encode("ascii")).hexdigest()
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.medical_parse_request_id', :value, true)"),
                {"value": str(request_id)},
            )
            probe = db.scalar(
                select(MedicalParseRequest).where(MedicalParseRequest.id == request_id)
            )
            if probe is None:
                raise Problem(409, "PARSE_REQUEST_STALE", "Parse request is no longer active")
            self._lock_patient_consent_fence(db, probe.patient_id)
            self._require_medical_analysis_consents(db, probe.patient_id)
            req = db.scalar(
                select(MedicalParseRequest)
                .where(MedicalParseRequest.id == request_id)
                .with_for_update()
            )
            if req is not None and req.callback_id == callback_id and req.status == "failed":
                if req.callback_hash != callback_hash:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Callback ID was reused")
                return
            if req is None or req.status not in {"pending", "processing"}:
                raise Problem(409, "PARSE_REQUEST_STALE", "Parse request is no longer active")
            doc = db.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.id == req.document_id,
                    MedicalDocument.patient_id == req.patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
            )
            if doc is None or doc.record_version != req.record_version:
                raise Problem(
                    409, "PARSE_REQUEST_STALE", "Source document changed or is unavailable"
                )
            req.status = "failed"
            req.callback_id = callback_id
            req.callback_hash = callback_hash
            req.finished_at = datetime.now(UTC)
            doc.parse_status = "failed"

    def claim_medical_parse_request(self) -> UUID | None:
        sessions = self._worker_sessions or self._sessions
        with sessions.begin() as db:
            probe = db.execute(
                select(MedicalParseRequest.id, MedicalParseRequest.patient_id)
                .where(
                    or_(
                        MedicalParseRequest.status == "pending",
                        (MedicalParseRequest.status == "processing")
                        & (
                            MedicalParseRequest.claimed_at
                            < datetime.now(UTC) - timedelta(minutes=5)
                        ),
                    )
                )
                .order_by(MedicalParseRequest.created_at)
                .limit(1)
            ).first()
            if probe is None:
                return None
            self._lock_patient_consent_fence(db, probe.patient_id)
            try:
                self._require_medical_analysis_consents(db, probe.patient_id)
            except Problem as error:
                if error.code != "CONSENT_REQUIRED":
                    raise
                stale = db.scalar(
                    select(MedicalParseRequest)
                    .where(MedicalParseRequest.id == probe.id)
                    .with_for_update(skip_locked=True)
                )
                if stale is not None:
                    stale.status = "invalidated"
                    stale.finished_at = datetime.now(UTC)
                    db.execute(
                        update(MedicalFieldCandidate)
                        .where(MedicalFieldCandidate.request_id == stale.id)
                        .values(excerpt=None, source_locator=None, review_status="invalidated")
                    )
                return None
            req = db.scalar(
                select(MedicalParseRequest)
                .where(
                    MedicalParseRequest.id == probe.id,
                    or_(
                        MedicalParseRequest.status == "pending",
                        (MedicalParseRequest.status == "processing")
                        & (
                            MedicalParseRequest.claimed_at
                            < datetime.now(UTC) - timedelta(minutes=5)
                        ),
                    ),
                )
                .with_for_update(skip_locked=True)
            )
            if req is None:
                return None
            now = datetime.now(UTC)
            req.status = "processing"
            req.claimed_at = now
            db.execute(
                update(MedicalDocument)
                .where(
                    MedicalDocument.id == req.document_id,
                    MedicalDocument.patient_id == req.patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
                .values(parse_status="processing")
            )
            return req.id

    def list_medical_candidates(
        self, context: AuthContext, document_id: UUID
    ) -> list[MedicalCandidateData]:
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            doc = db.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.id == document_id,
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
            )
            if doc is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            candidates = list(
                db.scalars(
                    select(MedicalFieldCandidate)
                    .join(
                        MedicalParseRequest,
                        MedicalParseRequest.id == MedicalFieldCandidate.request_id,
                    )
                    .where(
                        MedicalParseRequest.document_id == document_id,
                        MedicalFieldCandidate.patient_id == patient_id,
                    )
                    .order_by(MedicalFieldCandidate.created_at)
                )
            )
            output = []
            for candidate in candidates:
                decision = db.scalar(
                    select(MedicalCandidateDecision)
                    .where(MedicalCandidateDecision.candidate_id == candidate.id)
                    .order_by(MedicalCandidateDecision.created_at.desc())
                    .limit(1)
                )
                output.append(
                    MedicalCandidateData(
                        id=candidate.id,
                        field_code=candidate.field_code,
                        value_type=candidate.value_type,
                        value=candidate.value,
                        unit=candidate.unit,
                        confidence=candidate.confidence,
                        uncertainty=candidate.uncertainty,
                        source_locator=candidate.source_locator,
                        excerpt=candidate.excerpt,
                        review_status=candidate.review_status,
                        record_version=candidate.record_version,
                        chosen_value=decision.chosen_value if decision else None,
                    )
                )
            return output

    def decide_medical_candidate(
        self,
        context: AuthContext,
        candidate_id: UUID,
        *,
        decision: str,
        record_version: int,
        idempotency_key: str,
        value: Any = None,
    ) -> None:
        if decision not in {"accept", "correct", "reject"} or not 8 <= len(idempotency_key) <= 128:
            raise Problem(422, "VALIDATION_ERROR", "Decision is invalid")
        if decision != "correct" and value is not None:
            raise Problem(
                422, "VALIDATION_ERROR", "Only a correction may provide a replacement value"
            )
        idempotency_hash = sha256(
            json.dumps(
                {
                    "action": decision,
                    "corrected_value": value if decision == "correct" else None,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            self._lock_patient_consent_fence(db, patient_id, shared=False)
            prior = db.scalar(
                select(MedicalCandidateDecisionIdempotency).where(
                    MedicalCandidateDecisionIdempotency.patient_id == patient_id,
                    MedicalCandidateDecisionIdempotency.idempotency_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.candidate_id != candidate_id or prior.request_hash != idempotency_hash:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Idempotency key was reused")
                return
            candidate_probe = db.scalar(
                select(MedicalFieldCandidate).where(
                    MedicalFieldCandidate.id == candidate_id,
                    MedicalFieldCandidate.patient_id == patient_id,
                )
            )
            if candidate_probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            req = db.scalar(
                select(MedicalParseRequest)
                .where(
                    MedicalParseRequest.id == candidate_probe.request_id,
                    MedicalParseRequest.patient_id == patient_id,
                )
                .with_for_update()
            )
            candidate = db.scalar(
                select(MedicalFieldCandidate)
                .where(
                    MedicalFieldCandidate.id == candidate_id,
                    MedicalFieldCandidate.patient_id == patient_id,
                )
                .with_for_update()
            )
            if candidate is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            prior = db.scalar(
                select(MedicalCandidateDecisionIdempotency).where(
                    MedicalCandidateDecisionIdempotency.patient_id == patient_id,
                    MedicalCandidateDecisionIdempotency.idempotency_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.candidate_id != candidate_id or prior.request_hash != idempotency_hash:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Idempotency key was reused")
                return
            if candidate.review_status != "pending" or candidate.record_version != record_version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Candidate has changed")
            doc = (
                db.scalar(
                    select(MedicalDocument).where(
                        MedicalDocument.id == req.document_id, MedicalDocument.deleted_at.is_(None)
                    )
                )
                if req
                else None
            )
            if req is None or doc is None or req.status == "invalidated":
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            chosen = candidate.value if decision == "accept" else value
            if decision == "correct":
                corrected = {
                    "field_code": candidate.field_code,
                    "value_type": candidate.value_type,
                    "value": chosen,
                    "unit": candidate.unit,
                    "confidence": None,
                    "uncertainty": "patient_corrected",
                    "source_locator": candidate.source_locator,
                    "excerpt": candidate.excerpt,
                }
                self.validate_medical_candidate(corrected)
            elif decision == "reject":
                chosen = None
            db.add(
                MedicalCandidateDecisionIdempotency(
                    patient_id=patient_id,
                    candidate_id=candidate_id,
                    idempotency_key=idempotency_key,
                    request_hash=idempotency_hash,
                    response_status=204,
                )
            )
            db.add(
                MedicalCandidateDecision(
                    patient_id=patient_id,
                    candidate_id=candidate_id,
                    decision=decision,
                    chosen_value=chosen,
                    expected_version=record_version,
                    idempotency_key=idempotency_key,
                )
            )
            candidate.review_status = {
                "accept": "accepted",
                "correct": "corrected",
                "reject": "rejected",
            }[decision]
            candidate.record_version += 1
            if decision != "reject":
                db.add(
                    ConfirmedMedicalFact(
                        patient_id=patient_id,
                        candidate_id=candidate.id,
                        field_code=candidate.field_code,
                        value_type=candidate.value_type,
                        value=chosen,
                        unit=candidate.unit,
                    )
                )
                db.flush()
                self._reconcile_medical_conflicts(db, patient_id)
            remaining = db.scalar(
                select(MedicalFieldCandidate.id)
                .where(
                    MedicalFieldCandidate.request_id == candidate.request_id,
                    MedicalFieldCandidate.review_status == "pending",
                )
                .limit(1)
            )
            if remaining is None:
                req.status = "succeeded"
                req.finished_at = datetime.now(UTC)
                doc.parse_status = "confirmed"

    def list_medical_fact_conflicts(
        self, context: AuthContext, *, status: str = "open"
    ) -> list[dict[str, Any]]:
        with self._sessions() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            query = select(MedicalFactConflict).where(MedicalFactConflict.patient_id == patient_id)
            if status != "all":
                query = query.where(MedicalFactConflict.status == status)
            return [
                self._conflict_dto(db, row)
                for row in db.scalars(
                    query.order_by(desc(MedicalFactConflict.created_at)).limit(100)
                )
            ]

    def get_medical_fact_conflict(self, context: AuthContext, conflict_id: UUID) -> dict[str, Any]:
        with self._sessions() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            conflict = db.scalar(
                select(MedicalFactConflict).where(
                    MedicalFactConflict.id == conflict_id,
                    MedicalFactConflict.patient_id == patient_id,
                )
            )
            if conflict is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._conflict_dto(db, conflict, detail=True)

    def resolve_medical_fact_conflict(
        self, context: AuthContext, conflict_id: UUID, *, record_version: int, idempotency_key: str
    ) -> dict[str, Any]:
        if not 8 <= len(idempotency_key) <= 128:
            raise Problem(422, "VALIDATION_ERROR", "Idempotency key is invalid")
        request_hash = sha256(f"keep_both:{record_version}".encode()).hexdigest()
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            self._lock_medical_conflict_fence(db, patient_id)
            conflict = db.scalar(
                select(MedicalFactConflict)
                .where(
                    MedicalFactConflict.id == conflict_id,
                    MedicalFactConflict.patient_id == patient_id,
                )
                .with_for_update()
            )
            if conflict is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if conflict.resolution_key == idempotency_key and conflict.request_hash == request_hash:
                return {
                    "id": str(conflict.id),
                    "status": conflict.status,
                    "record_version": conflict.record_version,
                    "resolution": conflict.resolution,
                }
            if conflict.resolution_key == idempotency_key:
                raise Problem(409, "IDEMPOTENCY_CONFLICT", "Idempotency key was reused")
            if conflict.status != "open" or conflict.record_version != record_version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Conflict has changed")
            conflict.status = "resolved"
            conflict.resolution = "keep_both"
            conflict.resolution_key = idempotency_key
            conflict.request_hash = request_hash
            conflict.resolved_at = datetime.now(UTC)
            conflict.record_version += 1
            return {
                "id": str(conflict.id),
                "status": conflict.status,
                "record_version": conflict.record_version,
                "resolution": conflict.resolution,
            }

    @staticmethod
    def _conflict_dto(
        db: Session, conflict: MedicalFactConflict, *, detail: bool = False
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": str(conflict.id),
            "status": conflict.status,
            "record_version": conflict.record_version,
            "created_at": conflict.created_at,
            "resolution": conflict.resolution,
        }
        if detail:
            members = db.scalars(
                select(MedicalFactConflictMember).where(
                    MedicalFactConflictMember.conflict_id == conflict.id,
                    MedicalFactConflictMember.patient_id == conflict.patient_id,
                )
            ).all()
            result["members"] = []
            for member in members:
                fact = db.get(ConfirmedMedicalFact, member.fact_id)
                if fact is not None:
                    result["members"].append(
                        {
                            "fact_id": str(fact.id),
                            "source_document_id": str(member.document_id),
                            "field_code": fact.field_code,
                            "value": fact.value,
                            "unit": fact.unit,
                            "sampled_on": member.sampled_on,
                        }
                    )
        return result

    @staticmethod
    def _lock_medical_conflict_fence(db: Session, patient_id: UUID) -> None:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"f02-medical-conflict:{patient_id}"},
        )

    @staticmethod
    def _reconcile_medical_conflicts(db: Session, patient_id: UUID) -> None:
        """Rebuild conservative same-day lab-result conflicts from confirmed facts only."""
        FileService._lock_medical_conflict_fence(db, patient_id)
        query = (
            select(
                ConfirmedMedicalFact, MedicalFieldCandidate, MedicalParseRequest, MedicalDocument
            )
            .join(
                MedicalFieldCandidate, MedicalFieldCandidate.id == ConfirmedMedicalFact.candidate_id
            )
            .join(MedicalParseRequest, MedicalParseRequest.id == MedicalFieldCandidate.request_id)
            .join(MedicalDocument, MedicalDocument.id == MedicalParseRequest.document_id)
            .where(
                ConfirmedMedicalFact.patient_id == patient_id,
                ConfirmedMedicalFact.fact_status == "active",
                ConfirmedMedicalFact.field_code.in_(["test_item", "test_result"]),
                MedicalFieldCandidate.review_status.in_(["accepted", "corrected"]),
                MedicalDocument.deleted_at.is_(None),
            )
        )

        def norm_result(value: Any) -> tuple[str, str]:
            canonical = _canonical_decimal(value)
            if canonical is not None:
                return ("number", canonical)
            if isinstance(value, str):
                return ("text", _normal_text(value))
            return (
                "other",
                json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            )

        def norm(value: Any) -> str:
            if isinstance(value, str):
                return _normal_text(value)
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        by_doc: dict[
            UUID, dict[str, tuple[ConfirmedMedicalFact, MedicalFieldCandidate, MedicalDocument]]
        ] = {}
        for fact, candidate, _request, doc in db.execute(query):
            by_doc.setdefault(doc.id, {})[fact.field_code] = (fact, candidate, doc)
        groups: dict[tuple[str, str | None, date], list[tuple[Any, ...]]] = {}
        for fields in by_doc.values():
            if "test_item" not in fields or "test_result" not in fields:
                continue
            item_fact, item_candidate, doc = fields["test_item"]
            result_fact, result_candidate, _ = fields["test_result"]
            item = norm(item_fact.value)
            rv = result_fact.value if isinstance(result_fact.value, dict) else {}
            sampled_text = rv.get("sampled_on")
            if not sampled_text and doc.document_date:
                sampled_text = doc.document_date.isoformat()
            if not isinstance(sampled_text, str):
                continue
            sampled_on = date.fromisoformat(sampled_text)
            unit_value = rv.get("unit", result_fact.unit)
            unit = norm(unit_value) if unit_value not in (None, "") else None
            groups.setdefault((item, unit, sampled_on), []).append(
                (
                    doc,
                    item_fact,
                    item_candidate,
                    result_fact,
                    result_candidate,
                    norm_result(rv.get("result")),
                    sampled_on,
                )
            )
        active_hashes: set[str] = set()
        for group_key, members in groups.items():
            if len({m[0].id for m in members}) < 2 or len({m[5] for m in members}) < 2:
                continue
            group_hash = sha256(
                json.dumps(group_key, default=str, separators=(",", ":")).encode()
            ).hexdigest()
            active_hashes.add(group_hash)
            material = sorted((str(m[0].id), str(m[1].id), str(m[3].id)) for m in members)
            fingerprint = sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()
            conflict = db.scalar(
                select(MedicalFactConflict)
                .where(
                    MedicalFactConflict.patient_id == patient_id,
                    MedicalFactConflict.group_hash == group_hash,
                    MedicalFactConflict.status != "invalidated",
                )
                .with_for_update()
            )
            if conflict is None:
                conflict = MedicalFactConflict(
                    patient_id=patient_id,
                    group_hash=group_hash,
                    membership_fingerprint=fingerprint,
                    status="open",
                    record_version=1,
                )
                db.add(conflict)
                db.flush()
            else:
                if conflict.membership_fingerprint == fingerprint:
                    continue
                db.query(MedicalFactConflictMember).filter_by(
                    patient_id=patient_id, conflict_id=conflict.id
                ).delete(synchronize_session=False)
                conflict.membership_fingerprint = fingerprint
                conflict.record_version += 1
                if conflict.status == "resolved":
                    conflict.status = "open"
                    conflict.resolution = None
                    conflict.resolution_key = None
                    conflict.request_hash = None
                    conflict.resolved_at = None
            for (
                doc,
                item_fact,
                item_candidate,
                result_fact,
                result_candidate,
                _,
                sampled_on,
            ) in members:
                for fact, candidate, role in (
                    (item_fact, item_candidate, "test_item"),
                    (result_fact, result_candidate, "test_result"),
                ):
                    db.add(
                        MedicalFactConflictMember(
                            conflict_id=conflict.id,
                            patient_id=patient_id,
                            fact_id=fact.id,
                            document_id=doc.id,
                            member_role=role,
                            fact_version=candidate.record_version,
                            document_version=doc.record_version,
                            sampled_on=sampled_on,
                        )
                    )
        stale_open = (
            list(
                db.scalars(
                    select(MedicalFactConflict)
                    .where(
                        MedicalFactConflict.patient_id == patient_id,
                        MedicalFactConflict.status != "invalidated",
                        MedicalFactConflict.group_hash.not_in(active_hashes),
                    )
                    .with_for_update()
                )
            )
            if active_hashes
            else list(
                db.scalars(
                    select(MedicalFactConflict)
                    .where(
                        MedicalFactConflict.patient_id == patient_id,
                        MedicalFactConflict.status != "invalidated",
                    )
                    .with_for_update()
                )
            )
        )
        for conflict in stale_open:
            conflict.status = "invalidated"
            conflict.resolution = None
            conflict.resolution_key = None
            conflict.request_hash = None
            conflict.resolved_at = None
            conflict.invalidation_reason_code = "source_changed"
            max_version = (
                db.scalar(
                    select(func.max(MedicalFactConflictMember.document_version)).where(
                        MedicalFactConflictMember.patient_id == patient_id,
                        MedicalFactConflictMember.conflict_id == conflict.id,
                    )
                )
                or 1
            )
            conflict.invalidated_source_version = max_version
            conflict.membership_fingerprint = sha256(
                f"invalidated:{conflict.id}:{conflict.record_version + 1}".encode()
            ).hexdigest()
            conflict.record_version += 1
            db.execute(
                delete(MedicalFactConflictMember).where(
                    MedicalFactConflictMember.patient_id == patient_id,
                    MedicalFactConflictMember.conflict_id == conflict.id,
                )
            )

    @staticmethod
    def _set_user_scope(db: Session, user_id: UUID) -> UUID:
        db.execute(text("SELECT set_config('app.user_id', :value, true)"), {"value": str(user_id)})
        patient_id = db.scalar(select(PatientProfile.id).where(PatientProfile.user_id == user_id))
        if patient_id is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        db.execute(
            text("SELECT set_config('app.patient_id', :value, true)"),
            {"value": str(patient_id)},
        )
        return patient_id

    @staticmethod
    def _require_consent(db: Session, patient_id: UUID, consent_type: str) -> None:
        decision = db.scalar(
            select(PatientConsent)
            .where(
                PatientConsent.patient_id == patient_id,
                PatientConsent.consent_type == consent_type,
            )
            .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
            .limit(1)
        )
        if decision is None or not decision.granted:
            raise Problem(409, "CONSENT_REQUIRED", "Required data processing consent is missing")

    @classmethod
    def _require_health_consent(cls, db: Session, patient_id: UUID) -> None:
        cls._require_consent(db, patient_id, "health_data_processing")

    @classmethod
    def _require_medical_analysis_consents(cls, db: Session, patient_id: UUID) -> None:
        cls._require_health_consent(db, patient_id)
        cls._require_consent(db, patient_id, "third_party_ai")

    @staticmethod
    def _lock_patient_consent_fence(db: Session, patient_id: UUID, *, shared: bool = True) -> None:
        db.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(patient_id)},
        )
        lock_function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        db.execute(
            text(
                f"SELECT {lock_function}(hashtextextended("
                "'gutcare.patient-consent-fence:' || :patient_id, 0))"
            ),
            {"patient_id": str(patient_id)},
        )

    @staticmethod
    def _queue_orphan_cleanup(
        db: Session, bucket: str, object_key: str, reason: str, patient_id: UUID
    ) -> None:
        db.add(
            FileOrphanCleanupJob(
                id=uuid4(),
                patient_id=patient_id,
                bucket_name=bucket,
                object_key=object_key,
                reason=reason,
                due_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
        )

    def create_upload(
        self,
        context: AuthContext,
        *,
        purpose: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        idempotency_key: str,
    ) -> tuple[UploadSessionData, str]:
        safe_name = _safe_filename(file_name)
        allowed_upload(content_type, safe_name, size_bytes)
        normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if not 8 <= len(idempotency_key) <= 128:
            raise Problem(422, "VALIDATION_ERROR", "Invalid Idempotency-Key")
        if purpose not in {"medical_document", "diet_image", "stool_image", "avatar"}:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported file purpose")
        if purpose != "medical_document" and normalized_type == "application/pdf":
            raise Problem(415, "UNSUPPORTED_MEDIA_TYPE", "This purpose accepts images only")
        request_hash = _request_hash(purpose, safe_name, normalized_type, size_bytes)
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            if purpose in {"medical_document", "diet_image", "stool_image"}:
                self._lock_patient_consent_fence(db, patient_id)
                self._require_health_consent(db, patient_id)
            if purpose in {"diet_image", "stool_image"}:
                self._require_consent(db, patient_id, "sensitive_image")
            prior = db.scalar(
                select(UploadSession).where(
                    UploadSession.patient_id == patient_id,
                    UploadSession.idempotency_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.request_hash != request_hash:
                    raise Problem(409, "IDEMPOTENCY_CONFLICT", "Idempotency key was reused")
                capability = self._upload_capability(prior.id, prior.request_hash)
                return UploadSessionData(
                    prior.id,
                    f"{self._public_base_url}/uploads/{capability}",
                    prior.expires_at,
                ), capability
            session_id = uuid4()
            capability = self._upload_capability(session_id, request_hash)
            expires_at = datetime.now(UTC) + UPLOAD_TTL
            row = UploadSession(
                id=session_id,
                patient_id=patient_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                purpose=purpose,
                bucket_name=self._bucket,
                object_key=f"{uuid4().hex}/{uuid4().hex}",
                capability_hash=capability_digest(capability),
                original_name=safe_name,
                content_type=content_type.split(";", maxsplit=1)[0].strip().lower(),
                expected_size_bytes=size_bytes,
                status="issued",
                expires_at=expires_at,
            )
            db.add(row)
            db.flush()
            data = UploadSessionData(
                upload_id=row.id,
                upload_url=f"{self._public_base_url}/uploads/{capability}",
                expires_at=expires_at,
            )
        return data, capability

    def accept_upload(
        self,
        context: AuthContext,
        capability: str,
        content: bytes,
        content_type: str,
    ) -> None:
        if len(content) == 0 or len(content) > 20 * 1024 * 1024:
            raise Problem(413, "FILE_SIZE_LIMIT_EXCEEDED", "File size limit exceeded")
        digest = capability_digest(capability)
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            self._require_health_consent(db, patient_id)
            row = db.scalar(
                select(UploadSession)
                .where(
                    UploadSession.patient_id == patient_id,
                    UploadSession.capability_hash == digest,
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.status != "issued" or row.expires_at <= datetime.now(UTC):
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.purpose in {"medical_document", "diet_image", "stool_image"}:
                self._require_health_consent(db, patient_id)
            if row.purpose in {"diet_image", "stool_image"}:
                self._require_consent(db, patient_id, "sensitive_image")
            failure: Problem | None = None
            if len(content) != row.expected_size_bytes:
                failure = Problem(422, "FILE_SIZE_MISMATCH", "Uploaded file size does not match")
            else:
                failure = None
            normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
            if failure is None and normalized_type != row.content_type:
                failure = Problem(
                    415, "UNSUPPORTED_MEDIA_TYPE", "Uploaded content type does not match"
                )
            if failure is not None:
                row.status = "failed"
            else:
                storage_failure: Problem | None = None
                try:
                    self._storage.put_object(
                        row.bucket_name, row.object_key, content, normalized_type
                    )
                except Exception:
                    row.status = "failed"
                    self._queue_orphan_cleanup(
                        db, row.bucket_name, row.object_key, "upload_write_failed", row.patient_id
                    )
                    storage_failure = Problem(
                        503, "FILE_STORAGE_UNAVAILABLE", "File storage is unavailable"
                    )
                else:
                    row.status = "uploaded"
                    storage_failure = None
        if failure is not None:
            raise failure
        if storage_failure is not None:
            raise storage_failure

    def complete_upload(self, context: AuthContext, upload_id: UUID) -> FileObjectData:
        # The first read lets us handle scanner/storage failures in a separate committed
        # transaction, while every ordinary completion remains serialized by a row lock.
        with self._sessions() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            row = db.scalar(
                select(UploadSession).where(
                    UploadSession.id == upload_id, UploadSession.patient_id == patient_id
                )
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.status == "completed" and row.file_object_id is not None:
                file_object = db.scalar(
                    select(FileObject).where(
                        FileObject.id == row.file_object_id,
                        FileObject.patient_id == patient_id,
                    )
                )
                if file_object is not None:
                    return FileObjectData(
                        file_object.id,
                        file_object.storage_status,
                        file_object.content_type,
                        file_object.size_bytes,
                    )
            if row.status != "uploaded" or row.expires_at <= datetime.now(UTC):
                raise Problem(409, "UPLOAD_SESSION_UNAVAILABLE", "Upload session unavailable")
            bucket, object_key, name = row.bucket_name, row.object_key, row.original_name
            expected_size, expected_type = row.expected_size_bytes, row.content_type
            purpose = row.purpose

        try:
            actual_size, actual_type = self._storage.head_object(bucket, object_key)
            if (
                actual_size != expected_size
                or actual_type.split(";", maxsplit=1)[0].lower() != expected_type
            ):
                raise Problem(
                    422, "FILE_METADATA_MISMATCH", "Uploaded file metadata does not match"
                )
            content = self._storage.read_object(bucket, object_key)
            validated = validate_file(content, expected_type, name)
            if not self._scanner.scan(content):
                raise Problem(
                    422, "MALWARE_DETECTED", "Uploaded file did not pass security scanning"
                )
        except ScannerUnavailable as exc:
            with self._sessions.begin() as db:
                patient_id = self._set_user_scope(db, context.user_id)
                db.execute(
                    update(UploadSession)
                    .where(UploadSession.id == upload_id, UploadSession.patient_id == patient_id)
                    .values(status="failed")
                )
            try:
                self._storage.delete_object(bucket, object_key)
            except Exception:
                with self._sessions.begin() as db:
                    self._set_user_scope(db, context.user_id)
                    self._queue_orphan_cleanup(
                        db, bucket, object_key, "scanner_unavailable", patient_id
                    )
                logger.warning("failed to remove rejected upload object")
            raise Problem(
                503, "MALWARE_SCANNER_UNAVAILABLE", "File scanning is temporarily unavailable"
            ) from exc
        except Problem:
            with self._sessions.begin() as db:
                patient_id = self._set_user_scope(db, context.user_id)
                db.execute(
                    update(UploadSession)
                    .where(UploadSession.id == upload_id, UploadSession.patient_id == patient_id)
                    .values(status="failed")
                )
            try:
                self._storage.delete_object(bucket, object_key)
            except Exception:
                with self._sessions.begin() as db:
                    self._set_user_scope(db, context.user_id)
                    self._queue_orphan_cleanup(
                        db, bucket, object_key, "upload_rejected", patient_id
                    )
                logger.warning("failed to remove rejected upload object")
            raise
        except Exception as exc:
            with self._sessions.begin() as db:
                patient_id = self._set_user_scope(db, context.user_id)
                db.execute(
                    update(UploadSession)
                    .where(UploadSession.id == upload_id, UploadSession.patient_id == patient_id)
                    .values(status="failed")
                )
                self._queue_orphan_cleanup(
                    db, bucket, object_key, "verification_failed", patient_id
                )
            raise Problem(503, "FILE_STORAGE_UNAVAILABLE", "File storage is unavailable") from exc

        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            row = db.scalar(
                select(UploadSession)
                .where(UploadSession.id == upload_id, UploadSession.patient_id == patient_id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.status == "completed" and row.file_object_id is not None:
                file_object = db.scalar(
                    select(FileObject).where(FileObject.id == row.file_object_id)
                )
                if file_object is not None:
                    return FileObjectData(
                        file_object.id,
                        file_object.storage_status,
                        file_object.content_type,
                        file_object.size_bytes,
                    )
            if row.status != "uploaded":
                raise Problem(409, "UPLOAD_SESSION_UNAVAILABLE", "Upload session unavailable")
            file_object = FileObject(
                patient_id=patient_id,
                bucket_name=bucket,
                object_key=object_key,
                original_name=name,
                content_type=validated.content_type,
                size_bytes=validated.size_bytes,
                content_sha256=validated.content_sha256,
                sensitivity="medical"
                if purpose == "medical_document"
                else "sensitive_image"
                if purpose in {"diet_image", "stool_image"}
                else "normal",
                scan_status="clean",
                storage_status="available",
            )
            db.add(file_object)
            db.flush()
            row.file_object_id = file_object.id
            row.status = "completed"
            db.flush()
            return FileObjectData(
                file_object.id,
                file_object.storage_status,
                file_object.content_type,
                file_object.size_bytes,
            )

    def create_medical_document(
        self,
        context: AuthContext,
        *,
        file_object_id: UUID,
        document_type: str,
        hospital_name: str | None,
        document_date: date | None,
        notes: str | None,
        processing_mode: str,
    ) -> MedicalDocumentData:
        if document_type not in {
            "outpatient_record",
            "discharge_summary",
            "diagnosis_certificate",
            "lab_report",
            "prescription",
            "other",
        }:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported medical document type")
        if processing_mode not in {"store_only", "analyze"}:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported processing mode")
        if hospital_name is not None and len(hospital_name) > 160:
            raise Problem(422, "VALIDATION_ERROR", "Hospital name is too long")
        if notes is not None and len(notes) > 1000:
            raise Problem(422, "VALIDATION_ERROR", "Document notes are too long")
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            if processing_mode == "analyze":
                self._lock_patient_consent_fence(db, patient_id)
            self._require_health_consent(db, patient_id)
            if processing_mode == "analyze":
                self._require_consent(db, patient_id, "third_party_ai")
            file_object = db.scalar(
                select(FileObject).where(
                    FileObject.id == file_object_id,
                    FileObject.patient_id == patient_id,
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if file_object is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if file_object.sensitivity != "medical":
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if db.scalar(
                select(MedicalDocument.id).where(MedicalDocument.file_object_id == file_object_id)
            ):
                raise Problem(
                    409, "DOCUMENT_ALREADY_LINKED", "File is already linked to a document"
                )
            document = MedicalDocument(
                patient_id=patient_id,
                file_object_id=file_object_id,
                document_type=document_type,
                hospital_name=hospital_name,
                document_date=document_date,
                notes=notes,
                processing_mode=processing_mode,
                parse_status="pending" if processing_mode == "analyze" else "not_requested",
                record_version=1,
            )
            db.add(document)
            db.flush()
            if processing_mode == "analyze":
                db.add(
                    MedicalParseRequest(
                        patient_id=patient_id,
                        document_id=document.id,
                        file_object_id=file_object.id,
                        record_version=document.record_version,
                        status="pending",
                    )
                )
            return _document_data(document, file_object)

    def list_medical_documents(
        self,
        context: AuthContext,
        *,
        limit: int = 20,
        cursor: str | None = None,
        document_type: str | None = None,
    ) -> DocumentPageData:
        if not 1 <= limit <= 100:
            raise Problem(422, "VALIDATION_ERROR", "Invalid page size")
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            try:
                decoded = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
                raw_time, raw_id = decoded.split("|", 1)
                cursor_time = datetime.fromisoformat(raw_time)
                cursor_id = UUID(raw_id)
            except (ValueError, UnicodeDecodeError):
                raise Problem(422, "VALIDATION_ERROR", "Invalid cursor") from None
        with self._sessions() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            query = (
                select(MedicalDocument, FileObject)
                .join(
                    FileObject,
                    (FileObject.id == MedicalDocument.file_object_id)
                    & (FileObject.patient_id == MedicalDocument.patient_id),
                )
                .where(
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if document_type:
                query = query.where(MedicalDocument.document_type == document_type)
            if cursor_time is not None and cursor_id is not None:
                query = query.where(
                    (MedicalDocument.created_at < cursor_time)
                    | (
                        (MedicalDocument.created_at == cursor_time)
                        & (MedicalDocument.id < cursor_id)
                    )
                )
            rows = db.execute(
                query.order_by(desc(MedicalDocument.created_at), desc(MedicalDocument.id)).limit(
                    limit + 1
                )
            ).all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            items = [_document_data(document, file_object) for document, file_object in rows]
            next_cursor = None
            if has_more and rows:
                last_document = rows[-1][0]
                payload = f"{last_document.created_at.isoformat()}|{last_document.id}".encode()
                next_cursor = urlsafe_b64encode(payload).decode().rstrip("=")
            return DocumentPageData(items, next_cursor)

    def get_medical_document(self, context: AuthContext, document_id: UUID) -> MedicalDocumentData:
        with self._sessions() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            row = db.execute(
                select(MedicalDocument, FileObject)
                .join(
                    FileObject,
                    (FileObject.id == MedicalDocument.file_object_id)
                    & (FileObject.patient_id == MedicalDocument.patient_id),
                )
                .where(
                    MedicalDocument.id == document_id,
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            ).one_or_none()
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return _document_data(*row)

    def patch_medical_document(
        self,
        context: AuthContext,
        document_id: UUID,
        *,
        record_version: int,
        changes: dict[str, Any],
    ) -> MedicalDocumentData:
        allowed_fields = {"document_type", "hospital_name", "document_date", "notes"}
        if set(changes) - allowed_fields:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported document fields")
        if "document_type" in changes and changes["document_type"] not in {
            "outpatient_record",
            "discharge_summary",
            "diagnosis_certificate",
            "lab_report",
            "prescription",
            "other",
        }:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported medical document type")
        if changes.get("hospital_name") is not None and len(changes["hospital_name"]) > 160:
            raise Problem(422, "VALIDATION_ERROR", "Hospital name is too long")
        if changes.get("notes") is not None and len(changes["notes"]) > 1000:
            raise Problem(422, "VALIDATION_ERROR", "Document notes are too long")
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            self._lock_patient_consent_fence(db, patient_id, shared=False)
            self._lock_medical_conflict_fence(db, patient_id)
            document = db.scalar(
                select(MedicalDocument)
                .where(
                    MedicalDocument.id == document_id,
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if document is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if document.record_version != record_version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Document version conflict")
            changed = False
            for key, value in changes.items():
                if getattr(document, key) != value:
                    setattr(document, key, value)
                    changed = True
            if changed:
                document.record_version += 1
                document.updated_at = datetime.now(UTC)
                request_ids = select(MedicalParseRequest.id).where(
                    MedicalParseRequest.patient_id == patient_id,
                    MedicalParseRequest.document_id == document.id,
                )
                if set(changes) != {"document_date"}:
                    db.execute(
                        update(MedicalParseRequest)
                        .where(MedicalParseRequest.id.in_(request_ids))
                        .values(status="invalidated", finished_at=document.updated_at)
                    )
                    db.execute(
                        update(MedicalFieldCandidate)
                        .where(
                            MedicalFieldCandidate.patient_id == patient_id,
                            MedicalFieldCandidate.request_id.in_(request_ids),
                        )
                        .values(excerpt=None, source_locator=None, review_status="invalidated")
                    )
                if "document_date" in changes:
                    self._reconcile_medical_conflicts(db, patient_id)
            db.flush()
            file_object = db.scalar(
                select(FileObject).where(FileObject.id == document.file_object_id)
            )
            if file_object is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return _document_data(document, file_object)

    def delete_medical_document(self, context: AuthContext, document_id: UUID) -> None:
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            self._lock_patient_consent_fence(db, patient_id, shared=False)
            self._lock_medical_conflict_fence(db, patient_id)
            document = db.scalar(
                select(MedicalDocument)
                .where(
                    MedicalDocument.id == document_id,
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if document is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            file_object = db.scalar(
                select(FileObject)
                .where(
                    FileObject.id == document.file_object_id, FileObject.patient_id == patient_id
                )
                .with_for_update()
            )
            if file_object is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            now = datetime.now(UTC)
            affected_conflict_ids = list(
                db.scalars(
                    select(MedicalFactConflict.id)
                    .join(
                        MedicalFactConflictMember,
                        MedicalFactConflictMember.conflict_id == MedicalFactConflict.id,
                    )
                    .where(
                        MedicalFactConflict.patient_id == patient_id,
                        MedicalFactConflict.status.in_(["open", "resolved"]),
                        MedicalFactConflictMember.document_id == document.id,
                    )
                    .distinct()
                )
            )
            if affected_conflict_ids:
                invalidated_ids = list(
                    db.scalars(
                        update(MedicalFactConflict)
                        .where(
                            MedicalFactConflict.patient_id == patient_id,
                            MedicalFactConflict.id.in_(affected_conflict_ids),
                            MedicalFactConflict.status.in_(["open", "resolved"]),
                        )
                        .values(
                            status="invalidated",
                            resolution=None,
                            resolution_key=None,
                            request_hash=None,
                            resolved_at=None,
                            invalidation_reason_code="source_deleted",
                            invalidated_source_version=document.record_version,
                            membership_fingerprint=sha256(
                                f"invalidated:{document.id}:{now.isoformat()}".encode()
                            ).hexdigest(),
                            record_version=MedicalFactConflict.record_version + 1,
                            updated_at=now,
                        )
                        .returning(MedicalFactConflict.id)
                    )
                )
                db.execute(
                    delete(MedicalFactConflictMember).where(
                        MedicalFactConflictMember.patient_id == patient_id,
                        MedicalFactConflictMember.conflict_id.in_(invalidated_ids),
                    )
                )
                db.execute(
                    update(ConfirmedMedicalFact)
                    .where(
                        ConfirmedMedicalFact.patient_id == patient_id,
                        ConfirmedMedicalFact.candidate_id.in_(
                            select(MedicalFieldCandidate.id).where(
                                MedicalFieldCandidate.patient_id == patient_id,
                                MedicalFieldCandidate.request_id.in_(
                                    select(MedicalParseRequest.id).where(
                                        MedicalParseRequest.patient_id == patient_id,
                                        MedicalParseRequest.document_id == document.id,
                                    )
                                ),
                            )
                        ),
                    )
                    .values(fact_status="source_deleted")
                )
            request_ids = list(
                db.scalars(
                    text(
                        "UPDATE health.medical_parse_request "
                        "SET status = 'invalidated', finished_at = :now, "
                        "document_id = NULL, file_object_id = NULL "
                        "WHERE patient_id = :patient_id AND document_id = :document_id "
                        "RETURNING id"
                    ),
                    {
                        "now": now,
                        "patient_id": patient_id,
                        "document_id": document.id,
                    },
                )
            )
            if document.processing_mode == "analyze" and not request_ids:
                raise Problem(
                    500, "PARSE_SOURCE_INVALIDATION_FAILED", "Parse source link is missing"
                )
            db.execute(
                text(
                    "UPDATE health.medical_field_candidate "
                    "SET excerpt = NULL, source_locator = NULL, review_status = 'invalidated' "
                    "WHERE patient_id = :patient_id AND request_id = ANY(:request_ids)"
                ),
                {"patient_id": patient_id, "request_ids": request_ids},
            )
            db.execute(
                update(MedicationSourceRef)
                .where(
                    MedicationSourceRef.patient_id == patient_id,
                    MedicationSourceRef.live_document_id == document.id,
                )
                .values(live_document_id=None, source_deleted_at=now)
            )
            self._redact_plan_create_snapshots(db, patient_id, document.id)
            document.deleted_at = now
            document.updated_at = now
            file_object.deleted_at = now
            file_object.storage_status = "deleting"
            db.add(
                FileDeletionJob(
                    id=uuid4(),
                    patient_id=patient_id,
                    file_object_id=file_object.id,
                    bucket_name=file_object.bucket_name,
                    object_key=file_object.object_key,
                    due_at=now + DELETE_GRACE,
                    status="pending",
                    attempts=0,
                    created_at=now,
                )
            )

    def create_download_grant(self, context: AuthContext, file_id: UUID) -> DownloadGrantData:
        capability = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + DOWNLOAD_TTL
        with self._sessions.begin() as db:
            patient_id = self._set_user_scope(db, context.user_id)
            file_object = db.scalar(
                select(FileObject).where(
                    FileObject.id == file_id,
                    FileObject.patient_id == patient_id,
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if file_object is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            self._require_health_consent(db, patient_id)
            db.add(
                FileDownloadGrant(
                    patient_id=patient_id,
                    file_object_id=file_id,
                    token_hash=capability_digest(capability),
                    expires_at=expires_at,
                )
            )
        return DownloadGrantData(
            download_url=f"{self._public_base_url}/uploads/{capability}",
            expires_at=expires_at,
        )

    def download_by_capability(self, capability: str) -> tuple[bytes, str, str]:
        if len(capability) < 32:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        digest = capability_digest(capability)
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.download_capability_hash', :value, true)"),
                {"value": digest},
            )
            grant = db.scalar(
                select(FileDownloadGrant).where(
                    FileDownloadGrant.token_hash == digest,
                    FileDownloadGrant.expires_at > datetime.now(UTC),
                )
            )
            if grant is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            patient_id, file_id = grant.patient_id, grant.file_object_id
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"),
                {"value": str(patient_id)},
            )
            file_object = db.scalar(
                select(FileObject).where(
                    FileObject.id == file_id,
                    FileObject.patient_id == patient_id,
                    FileObject.storage_status == "available",
                    FileObject.deleted_at.is_(None),
                )
            )
            if file_object is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            bucket, object_key = file_object.bucket_name, file_object.object_key
            content_type, original_name = file_object.content_type, file_object.original_name
        try:
            content = self._storage.read_object(bucket, object_key)
        except Exception as exc:
            raise Problem(503, "FILE_STORAGE_UNAVAILABLE", "File storage is unavailable") from exc
        return content, content_type, original_name

    def process_deletion_job(self, job_id: UUID) -> bool:
        if self._worker_sessions is None:
            raise RuntimeError("A least-privilege worker database session is required")
        with self._worker_sessions.begin() as db:
            job = db.scalar(
                select(FileDeletionJob)
                .where(
                    FileDeletionJob.id == job_id,
                    (
                        (FileDeletionJob.status == "pending")
                        & (FileDeletionJob.due_at <= datetime.now(UTC))
                    )
                    | (
                        (FileDeletionJob.status == "processing")
                        & (FileDeletionJob.locked_at < datetime.now(UTC) - timedelta(minutes=5))
                    ),
                )
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return False
            job.status = "processing"
            job.locked_at = datetime.now(UTC)
            patient_id = job.patient_id
            file_id = job.file_object_id
            bucket = job.bucket_name
            object_key = job.object_key
        try:
            self._storage.delete_object(bucket, object_key)
        except Exception:
            with self._worker_sessions.begin() as db:
                job = db.get(FileDeletionJob, job_id)
                if job is not None:
                    job.attempts += 1
                    job.status = "pending"
                    job.locked_at = None
                    job.due_at = datetime.now(UTC) + timedelta(
                        seconds=min(3600, 30 * (2 ** min(job.attempts, 7)))
                    )
            logger.warning("file object deletion failed; job scheduled for retry")
            return False
        with self._worker_sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id', :value, true)"),
                {"value": str(patient_id)},
            )
            db.execute(
                text(
                    "DELETE FROM health.file_download_grant "
                    "WHERE file_object_id = :file_id AND patient_id = :patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text("""UPDATE health.medication_idempotency
                    SET response_snapshot = jsonb_set(
                      jsonb_set(response_snapshot, '{source_document_id}', 'null'::jsonb, true),
                      '{source_deleted}', 'true'::jsonb, true)
                    WHERE patient_id = :patient_id
                      AND route = 'POST:/medication-plans'
                      AND response_snapshot->>'source_document_id' IN (
                        SELECT id::text FROM health.medical_document
                        WHERE file_object_id = :file_id AND patient_id = :patient_id
                      )"""),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                update(MedicationSourceRef)
                .where(
                    MedicationSourceRef.patient_id == patient_id,
                    MedicationSourceRef.live_document_id.in_(
                        select(MedicalDocument.id).where(
                            MedicalDocument.file_object_id == file_id,
                            MedicalDocument.patient_id == patient_id,
                        )
                    ),
                )
                .values(live_document_id=None, source_deleted_at=datetime.now(UTC))
            )
            db.execute(
                text(
                    "DELETE FROM health.medical_document "
                    "WHERE file_object_id = :file_id AND patient_id = :patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text(
                    "DELETE FROM health.upload_session "
                    "WHERE file_object_id = :file_id AND patient_id = :patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text(
                    "DELETE FROM health.diet_record_image WHERE file_object_id=:file_id AND patient_id=:patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text(
                    "DELETE FROM health.stool_record_image WHERE file_object_id=:file_id AND patient_id=:patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text(
                    "DELETE FROM health.file_object "
                    "WHERE id = :file_id AND patient_id = :patient_id"
                ),
                {"file_id": file_id, "patient_id": patient_id},
            )
            db.execute(
                text("DELETE FROM integration.file_deletion_job WHERE id = :job_id"),
                {"job_id": job_id},
            )
        return True

    @staticmethod
    def _redact_plan_create_snapshots(db: Session, patient_id: UUID, document_id: UUID) -> None:
        db.execute(
            text("""UPDATE health.medication_idempotency
                SET response_snapshot = jsonb_set(
                  jsonb_set(response_snapshot, '{source_document_id}', 'null'::jsonb, true),
                  '{source_deleted}', 'true'::jsonb, true)
                WHERE patient_id = :patient_id
                  AND route = 'POST:/medication-plans'
                  AND response_snapshot->>'source_document_id' = :document_id"""),
            {"patient_id": patient_id, "document_id": str(document_id)},
        )

    def process_due_deletion_jobs(self, *, limit: int = 50) -> int:
        """Drain due cleanup jobs; expired processing leases are recovered idempotently."""
        if self._worker_sessions is None:
            raise RuntimeError("A least-privilege worker database session is required")
        with self._worker_sessions() as db:
            job_ids = list(
                db.scalars(
                    select(FileDeletionJob.id)
                    .where(
                        (FileDeletionJob.status == "pending")
                        & (FileDeletionJob.due_at <= datetime.now(UTC))
                        | (
                            (FileDeletionJob.status == "processing")
                            & (FileDeletionJob.locked_at < datetime.now(UTC) - timedelta(minutes=5))
                        )
                    )
                    .order_by(FileDeletionJob.due_at)
                    .limit(limit)
                )
            )
        completed = sum(self.process_deletion_job(job_id) for job_id in job_ids)
        return completed + self.process_due_orphan_cleanups(limit=limit)

    def reap_expired_upload_sessions(self, *, limit: int = 100) -> int:
        if self._worker_sessions is None:
            raise RuntimeError("A least-privilege worker database session is required")
        now = datetime.now(UTC)
        with self._worker_sessions.begin() as db:
            rows = list(
                db.scalars(
                    select(UploadSession)
                    .where(
                        UploadSession.status.in_(("issued", "uploaded")),
                        UploadSession.expires_at <= now,
                    )
                    .order_by(UploadSession.expires_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for row in rows:
                was_uploaded = row.status == "uploaded"
                db.execute(
                    text("SELECT set_config('app.patient_id', :value, true)"),
                    {"value": str(row.patient_id)},
                )
                row.status = "expired"
                if was_uploaded:
                    self._queue_orphan_cleanup(
                        db, row.bucket_name, row.object_key, "expired_upload", row.patient_id
                    )
            return len(rows)

    def process_due_orphan_cleanups(self, *, limit: int = 100) -> int:
        if self._worker_sessions is None:
            raise RuntimeError("A least-privilege worker database session is required")
        lease_expired = datetime.now(UTC) - timedelta(minutes=5)
        with self._worker_sessions.begin() as db:
            jobs = list(
                db.scalars(
                    select(FileOrphanCleanupJob)
                    .where(
                        (FileOrphanCleanupJob.status == "pending")
                        & (FileOrphanCleanupJob.due_at <= datetime.now(UTC))
                        | (
                            (FileOrphanCleanupJob.status == "processing")
                            & (FileOrphanCleanupJob.locked_at < lease_expired)
                        )
                    )
                    .order_by(FileOrphanCleanupJob.due_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in jobs:
                job.status = "processing"
                job.locked_at = datetime.now(UTC)
            work = [(job.id, job.bucket_name, job.object_key, job.attempts) for job in jobs]
        removed = 0
        for job_id, bucket, object_key, attempts in work:
            try:
                self._storage.delete_object(bucket, object_key)
            except Exception:
                with self._worker_sessions.begin() as db:
                    cleanup_job = db.get(FileOrphanCleanupJob, job_id)
                    if cleanup_job is not None:
                        cleanup_job.status = "pending"
                        cleanup_job.locked_at = None
                        cleanup_job.attempts = attempts + 1
                        cleanup_job.due_at = datetime.now(UTC) + timedelta(
                            seconds=min(3600, 30 * (2 ** min(cleanup_job.attempts, 7)))
                        )
            else:
                with self._worker_sessions.begin() as db:
                    db.execute(
                        text("DELETE FROM integration.file_orphan_cleanup_job WHERE id = :id"),
                        {"id": job_id},
                    )
                removed += 1
        return removed
