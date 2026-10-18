"""Business-worker APIs for frozen record-image recognition inputs."""
# ruff: noqa: E501 -- SQL statements mirror the locked worker contract.

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from gutcare.shared.errors import Problem

worker_router = APIRouter(prefix="/internal/v1", tags=["Record Image Worker"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


ImageCoordinate = Annotated[float, Field(ge=0, le=1)]


class DietCandidate(StrictBody):
    candidate_id: UUID
    attachment_id: UUID
    candidate_group_key: UUID
    candidate_type: Literal["food_name", "food_category", "portion_description"]
    value: str = Field(min_length=1, max_length=160)
    confidence_band: Literal["low", "medium", "high"]
    uncertainty_code: Literal[
        "partially_occluded", "mixed_food", "low_light", "ambiguous_shape", "image_quality", "other"
    ]
    image_region: (
        tuple[ImageCoordinate, ImageCoordinate, ImageCoordinate, ImageCoordinate] | None
    ) = None


class StoolCandidate(StrictBody):
    candidate_id: UUID
    attachment_id: UUID
    candidate_type: Literal["bristol_type"]
    value: int = Field(ge=1, le=7)
    confidence_band: Literal["low", "medium", "high"]
    uncertainty_code: Literal[
        "partially_occluded", "mixed_food", "low_light", "ambiguous_shape", "image_quality", "other"
    ]
    image_region: (
        tuple[ImageCoordinate, ImageCoordinate, ImageCoordinate, ImageCoordinate] | None
    ) = None


class RecognitionImageResult(StrictBody):
    attachment_id: UUID
    image_quality: Literal["usable", "unusable", "uncertain"]
    reason_code: (
        Literal[
            "low_image_quality", "unsupported_image", "no_visible_food", "no_reliable_stool_type"
        ]
        | None
    ) = None
    candidates: list[DietCandidate | StoolCandidate] = Field(max_length=50)


class CandidateSubmission(StrictBody):
    callback_id: UUID
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)
    schema_version: Literal["1.0"]
    images: list[RecognitionImageResult] = Field(min_length=1, max_length=10)


class RecognitionFailure(StrictBody):
    callback_id: UUID
    error_code: Literal[
        "agent_unavailable", "timeout", "invalid_image", "internal_processing_error"
    ]


def _agent(request: Request, authorization: str | None) -> None:
    token = request.app.state.settings.agent_service_token
    if (
        not token
        or not authorization
        or not authorization.startswith("Bearer ")
        or not hmac.compare_digest(authorization[7:], token)
    ):
        raise Problem(401, "AUTHENTICATION_REQUIRED", "Service authentication required")


class RecordImageWorkerService:
    """Implements worker claim, frozen input, and one-time image capabilities."""

    def __init__(self, sessions: sessionmaker[Session], storage: Any) -> None:
        self._sessions = sessions
        self._storage = storage

    @staticmethod
    def _fence(db: Session, patient_id: UUID) -> None:
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
            ),
            {"p": str(patient_id)},
        )
        db.execute(text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient_id)})

    @staticmethod
    def _consent(db: Session, patient_id: UUID) -> bool:
        rows = db.execute(
            text(
                "SELECT DISTINCT ON (consent_type) consent_type,granted,revoked_at FROM health.patient_consent WHERE patient_id=:p AND consent_type IN ('health_data_processing','sensitive_image','third_party_ai') ORDER BY consent_type,decided_at DESC,id DESC"
            ),
            {"p": patient_id},
        ).mappings()
        latest = {row["consent_type"]: row for row in rows}
        return all(
            (row := latest.get(kind)) is not None and row["granted"] and row["revoked_at"] is None
            for kind in ("health_data_processing", "sensitive_image", "third_party_ai")
        )

    @staticmethod
    def _record(db: Session, patient_id: UUID, record_id: UUID, kind: str) -> Any:
        row = (
            db.execute(
                text("SELECT * FROM analysis.get_record_image_worker_context(:p,:r,:kind)"),
                {"r": record_id, "p": patient_id, "kind": kind},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        return row

    @staticmethod
    def _request(db: Session, request_id: UUID, patient_id: UUID) -> Any:
        row = (
            db.execute(
                text(
                    "SELECT id,patient_id,record_id,disclosure_id,recognition_type,status,attempt,retry_of_request_id,schema_version,record_version,decision_record_version,image_set_version,lease_until,callback_id,callback_hash FROM analysis.record_image_recognition_request WHERE id=:id AND patient_id=:p FOR UPDATE"
                ),
                {"id": request_id, "p": patient_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        return row

    @staticmethod
    def _disclosure_valid(db: Session, row: Any) -> bool:
        found = db.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM health.record_image_disclosure d WHERE d.id=:id AND d.patient_id=:p AND d.record_id=:r AND d.purpose=:purpose AND d.record_version=:rv AND d.image_set_version=:iv AND d.consumed_at IS NOT NULL)"
            ),
            {
                "id": row["disclosure_id"],
                "p": row["patient_id"],
                "r": row["record_id"],
                "purpose": row["recognition_type"],
                "rv": row["record_version"],
                "iv": row["image_set_version"],
            },
        )
        return bool(found)

    @staticmethod
    def _attachments(db: Session, row: Any) -> list[dict[str, Any]]:
        live = [
            dict(item)
            for item in db.execute(
                text(
                    "SELECT * FROM analysis.list_record_image_worker_attachments(:p,:r,:kind) ORDER BY attachment_position,attachment_id"
                ),
                {
                    "p": row["patient_id"],
                    "r": row["record_id"],
                    "kind": row["recognition_type"],
                },
            ).mappings()
        ]
        frozen_rows = list(
            db.execute(
                text("""SELECT position,file_version,
                  COALESCE(diet_attachment_id,stool_attachment_id) AS attachment_id
                  FROM analysis.record_image_request_attachment
                  WHERE request_id=:r AND patient_id=:p ORDER BY position"""),
                {"r": row["id"], "p": row["patient_id"]},
            ).mappings()
        )
        if len(live) != len(frozen_rows) or not live:
            return []
        by_id = {str(item["attachment_id"]): item for item in live}
        for frozen in frozen_rows:
            current = by_id.get(str(frozen["attachment_id"]))
            if (
                current is None
                or current["file_version"] != frozen["file_version"]
                or current["attachment_position"] != frozen["position"]
                or current["storage_status"] != "available"
                or current["scan_status"] != "clean"
            ):
                return []
        return live

    @staticmethod
    def _invalidate(db: Session, row: Any) -> None:
        db.execute(
            text(
                "UPDATE analysis.record_image_recognition_request SET status='invalidated',lease_until=NULL,updated_at=now() WHERE id=:id AND patient_id=:p"
            ),
            {"id": row["id"], "p": row["patient_id"]},
        )
        db.execute(
            text(
                "UPDATE analysis.record_image_candidate SET status='invalidated',value='null'::jsonb,locator=NULL WHERE request_id=:id AND patient_id=:p AND status='pending'"
            ),
            {"id": row["id"], "p": row["patient_id"]},
        )
        db.execute(
            text(
                "DELETE FROM analysis.record_image_capability WHERE request_id=:id AND patient_id=:p"
            ),
            {"id": row["id"], "p": row["patient_id"]},
        )

    def claim(self) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            probe = (
                db.execute(
                    text(
                        "SELECT id,patient_id,record_id,recognition_type,status FROM analysis.record_image_recognition_request WHERE status='pending' OR (status='processing' AND lease_until<=:now) ORDER BY created_at,id LIMIT 1"
                    ),
                    {"now": now},
                )
                .mappings()
                .first()
            )
            if probe is None:
                return None
            patient_id = probe["patient_id"]
            self._fence(db, patient_id)
            record = self._record(db, patient_id, probe["record_id"], probe["recognition_type"])
            row = (
                db.execute(
                    text(
                        "SELECT id,patient_id,record_id,disclosure_id,recognition_type,status,attempt,retry_of_request_id,schema_version,record_version,decision_record_version,image_set_version,lease_until FROM analysis.record_image_recognition_request WHERE id=:id AND patient_id=:p AND (status='pending' OR (status='processing' AND lease_until<=:now)) FOR UPDATE SKIP LOCKED"
                    ),
                    {"id": probe["id"], "p": patient_id, "now": now},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            valid = (
                self._consent(db, patient_id)
                and self._disclosure_valid(db, row)
                and record["record_version"] == row["decision_record_version"]
                and record["image_set_version"] == row["image_set_version"]
                and self._attachments(db, row)
            )
            if not valid:
                self._invalidate(db, row)
                return None
            # Request attempt is immutable across lease recovery; only an
            # explicit patient retry creates the next attempt in the chain.
            attempt = int(row["attempt"])
            db.execute(
                text(
                    "UPDATE analysis.record_image_recognition_request SET status='processing',attempt=:attempt,claimed_at=:now,lease_until=:lease,updated_at=:now WHERE id=:id AND patient_id=:p"
                ),
                {
                    "attempt": attempt,
                    "now": now,
                    "lease": now + timedelta(minutes=5),
                    "id": row["id"],
                    "p": patient_id,
                },
            )
            dispatch = {
                "request_id": str(row["id"]),
                "recognition_type": row["recognition_type"],
                "attempt": attempt,
                "retry_of_request_id": (
                    str(row["retry_of_request_id"]) if row["retry_of_request_id"] else None
                ),
                "schema_version": row["schema_version"],
            }
            db.execute(
                text("""
                    INSERT INTO analysis.record_image_dispatch_outbox(request_id,patient_id,attempt,payload)
                    VALUES (:id,:p,:attempt,CAST(:payload AS jsonb))
                    ON CONFLICT(request_id,attempt) DO UPDATE
                      SET status='pending',available_at=now(),lease_until=NULL,last_error_code=NULL
                      WHERE analysis.record_image_dispatch_outbox.status<>'dead_letter'
                """),
                {
                    "id": row["id"],
                    "p": patient_id,
                    "attempt": attempt,
                    "payload": json.dumps(dispatch),
                },
            )
            return dispatch

    def input(self, request_id: UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            probe = (
                db.execute(
                    text(
                        "SELECT id,patient_id,record_id,recognition_type FROM analysis.record_image_recognition_request WHERE id=:id"
                    ),
                    {"id": request_id},
                )
                .mappings()
                .first()
            )
            if probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            self._fence(db, probe["patient_id"])
            record = self._record(
                db, probe["patient_id"], probe["record_id"], probe["recognition_type"]
            )
            row = self._request(db, request_id, probe["patient_id"])
            if (
                row["status"] != "processing"
                or row["lease_until"] is None
                or row["lease_until"] <= now
                or not self._consent(db, row["patient_id"])
                or not self._disclosure_valid(db, row)
                or record["record_version"] != row["decision_record_version"]
                or record["image_set_version"] != row["image_set_version"]
            ):
                self._invalidate(db, row)
                raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
            attachments = self._attachments(db, row)
            if not attachments:
                self._invalidate(db, row)
                raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
            result_attachments: list[dict[str, Any]] = []
            for item in attachments:
                capability = secrets.token_urlsafe(48)
                capability_hash = hashlib.sha256(capability.encode()).hexdigest()
                db.execute(
                    text(
                        "DELETE FROM analysis.record_image_capability WHERE request_id=:r AND patient_id=:p AND attachment_id=:a"
                    ),
                    {"r": request_id, "p": row["patient_id"], "a": item["attachment_id"]},
                )
                db.execute(
                    text(
                        "INSERT INTO analysis.record_image_capability(capability_hash,request_id,patient_id,attachment_id,file_object_id,file_version,expires_at) VALUES (:hash,:r,:p,:a,:f,:v,:exp)"
                    ),
                    {
                        "hash": capability_hash,
                        "r": request_id,
                        "p": row["patient_id"],
                        "a": item["attachment_id"],
                        "f": item["file_object_id"],
                        "v": item["file_version"],
                        "exp": now + timedelta(minutes=1),
                    },
                )
                result_attachments.append(
                    {
                        "attachment_id": str(item["attachment_id"]),
                        "file_version": item["file_version"],
                        "content_type": item["content_type"],
                        "image_capability": capability,
                    }
                )
            context: dict[str, Any] = {"occurred_at": record["occurred_at"].isoformat()}
            if row["recognition_type"] == "diet_image_recognition":
                context["meal_type"] = record["meal_type"]
            else:
                context["bristol_type"] = record["bristol_type"]
            return {
                "request_id": str(request_id),
                "recognition_type": row["recognition_type"],
                "record_id": str(row["record_id"]),
                "record_version": row["record_version"],
                "image_set_version": row["image_set_version"],
                "attempt": row["attempt"],
                "retry_of_request_id": (
                    str(row["retry_of_request_id"]) if row["retry_of_request_id"] else None
                ),
                "schema_version": row["schema_version"],
                "context": context,
                "attachments": result_attachments,
            }

    @staticmethod
    def _callback_digest(body: BaseModel) -> str:
        encoded = json.dumps(
            body.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _callback_context(
        self,
        db: Session,
        request_id: UUID,
        record_version: int,
        image_set_version: int,
        callback_id: UUID,
        callback_hash: str,
    ) -> Any:
        probe = (
            db.execute(
                text(
                    "SELECT id,patient_id,record_id,recognition_type FROM analysis.record_image_recognition_request WHERE id=:id"
                ),
                {"id": request_id},
            )
            .mappings()
            .first()
        )
        if probe is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        self._fence(db, probe["patient_id"])
        record = self._record(
            db, probe["patient_id"], probe["record_id"], probe["recognition_type"]
        )
        row = self._request(db, request_id, probe["patient_id"])
        if row["callback_id"] is not None:
            if (
                row["callback_id"] == callback_id
                and row["callback_hash"] == callback_hash
                and self._consent(db, row["patient_id"])
                and self._disclosure_valid(db, row)
            ):
                return row, []
            raise Problem(
                409, "CALLBACK_CONFLICT", "Recognition callback conflicts with a prior result"
            )
        if (
            row["status"] != "processing"
            or row["lease_until"] is None
            or row["lease_until"] <= datetime.now(UTC)
            or not self._consent(db, row["patient_id"])
            or not self._disclosure_valid(db, row)
            or record["record_version"] != row["decision_record_version"]
            or record["image_set_version"] != row["image_set_version"]
            or record_version != row["record_version"]
            or image_set_version != row["image_set_version"]
        ):
            self._invalidate(db, row)
            raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
        live_attachments = self._attachments(db, row)
        if not live_attachments:
            self._invalidate(db, row)
            raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
        return row, live_attachments

    def submit_candidates(self, request_id: UUID, body: CandidateSubmission) -> None:
        digest = self._callback_digest(body)
        with self._sessions.begin() as db:
            row, live = self._callback_context(
                db,
                request_id,
                body.record_version,
                body.image_set_version,
                body.callback_id,
                digest,
            )
            if row["callback_id"] is not None:
                return
            by_attachment = {item["attachment_id"]: item for item in live}
            received: set[UUID] = set()
            candidate_ids: set[UUID] = set()
            group_types: set[tuple[UUID, str]] = set()
            prepared: list[dict[str, Any]] = []
            is_diet = row["recognition_type"] == "diet_image_recognition"
            if len(body.images) != len(live):
                raise Problem(
                    422,
                    "VALIDATION_ERROR",
                    "Callback images do not match the frozen attachment set",
                )
            for image in body.images:
                if image.attachment_id in received or image.attachment_id not in by_attachment:
                    raise Problem(
                        422, "VALIDATION_ERROR", "Callback attachment is not in the frozen set"
                    )
                received.add(image.attachment_id)
                for candidate in image.candidates:
                    if is_diet != isinstance(candidate, DietCandidate):
                        raise Problem(
                            422,
                            "VALIDATION_ERROR",
                            "Candidate type does not match recognition type",
                        )
                    if candidate.attachment_id != image.attachment_id:
                        raise Problem(
                            422, "VALIDATION_ERROR", "Candidate attachment does not match its image"
                        )
                    if candidate.candidate_id in candidate_ids:
                        raise Problem(
                            422, "VALIDATION_ERROR", "Candidate identifiers must be unique"
                        )
                    candidate_ids.add(candidate.candidate_id)
                    if isinstance(candidate, DietCandidate):
                        pair = (candidate.candidate_group_key, candidate.candidate_type)
                        if pair in group_types:
                            raise Problem(
                                422,
                                "VALIDATION_ERROR",
                                "A group may contain only one candidate per type",
                            )
                        group_types.add(pair)
                        if candidate.candidate_type == "food_category" and candidate.value not in {
                            "grain_staple",
                            "vegetable",
                            "fruit",
                            "meat",
                            "seafood",
                            "dairy",
                            "egg",
                            "legume",
                            "snack",
                            "beverage",
                            "mixed_dish",
                            "other",
                        }:
                            raise Problem(422, "VALIDATION_ERROR", "Food category is not supported")
                        group_key: UUID | None = candidate.candidate_group_key
                    else:
                        group_key = None
                    prepared.append(
                        {
                            "id": candidate.candidate_id,
                            "attachment": candidate.attachment_id,
                            "type": candidate.candidate_type,
                            "group": group_key,
                            "confidence": candidate.confidence_band,
                            "value": json.dumps(candidate.value, ensure_ascii=False),
                            "locator": json.dumps(candidate.image_region),
                            "uncertainty": candidate.uncertainty_code,
                        }
                    )
            if received != set(by_attachment):
                raise Problem(
                    422, "VALIDATION_ERROR", "Callback must include every frozen attachment"
                )
            for candidate_values in prepared:
                db.execute(
                    text(
                        "INSERT INTO analysis.record_image_candidate(id,request_id,patient_id,attachment_id,candidate_type,candidate_group_key,confidence_band,value,locator,uncertainty) VALUES (:id,:r,:p,:attachment,:type,:group,:confidence,CAST(:value AS jsonb),CAST(:locator AS jsonb),:uncertainty)"
                    ),
                    {
                        **candidate_values,
                        "r": request_id,
                        "p": row["patient_id"],
                    },
                )
            db.execute(
                text(
                    "UPDATE analysis.record_image_recognition_request SET status=:status,callback_id=:callback,callback_hash=:hash,lease_until=NULL,updated_at=now() WHERE id=:id AND patient_id=:p"
                ),
                {
                    "status": "candidates_ready" if prepared else "no_candidates",
                    "callback": body.callback_id,
                    "hash": digest,
                    "id": request_id,
                    "p": row["patient_id"],
                },
            )

    def fail(self, request_id: UUID, body: RecognitionFailure) -> None:
        digest = self._callback_digest(body)
        with self._sessions.begin() as db:
            probe = (
                db.execute(
                    text(
                        "SELECT id,patient_id,record_id,recognition_type,record_version,image_set_version FROM analysis.record_image_recognition_request WHERE id=:id"
                    ),
                    {"id": request_id},
                )
                .mappings()
                .first()
            )
            if probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            row, _live = self._callback_context(
                db,
                request_id,
                probe["record_version"],
                probe["image_set_version"],
                body.callback_id,
                digest,
            )
            if row["callback_id"] is not None:
                return
            db.execute(
                text(
                    "UPDATE analysis.record_image_recognition_request SET status='failed',failure_code=:code,callback_id=:callback,callback_hash=:hash,lease_until=NULL,updated_at=now() WHERE id=:id AND patient_id=:p"
                ),
                {
                    "code": body.error_code,
                    "callback": body.callback_id,
                    "hash": digest,
                    "id": request_id,
                    "p": row["patient_id"],
                },
            )
            db.execute(
                text(
                    "DELETE FROM analysis.record_image_capability WHERE request_id=:id AND patient_id=:p"
                ),
                {"id": request_id, "p": row["patient_id"]},
            )

    def read_image(self, raw_capability: str) -> tuple[bytes, str]:
        if len(raw_capability) < 32 or len(raw_capability) > 256:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        digest = hashlib.sha256(raw_capability.encode()).hexdigest()
        now = datetime.now(UTC)
        with self._sessions.begin() as db:
            probe = (
                db.execute(
                    text(
                        "SELECT c.request_id,c.patient_id,r.record_id,r.recognition_type FROM analysis.record_image_capability c JOIN analysis.record_image_recognition_request r ON r.id=c.request_id AND r.patient_id=c.patient_id WHERE c.capability_hash=:hash"
                    ),
                    {"hash": digest},
                )
                .mappings()
                .first()
            )
            if probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            self._fence(db, probe["patient_id"])
            record = self._record(
                db, probe["patient_id"], probe["record_id"], probe["recognition_type"]
            )
            row = self._request(db, probe["request_id"], probe["patient_id"])
            if (
                row["status"] != "processing"
                or row["lease_until"] is None
                or row["lease_until"] <= now
                or not self._consent(db, row["patient_id"])
                or not self._disclosure_valid(db, row)
                or record["record_version"] != row["decision_record_version"]
                or record["image_set_version"] != row["image_set_version"]
            ):
                self._invalidate(db, row)
                raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
            cap = (
                db.execute(
                    text(
                        "SELECT attachment_id,file_object_id,file_version FROM analysis.record_image_capability WHERE capability_hash=:hash AND request_id=:r AND patient_id=:p AND expires_at>:now AND consumed_at IS NULL FOR UPDATE"
                    ),
                    {"hash": digest, "r": row["id"], "p": row["patient_id"], "now": now},
                )
                .mappings()
                .first()
            )
            if cap is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            attachments = self._attachments(db, row)
            item = next(
                (item for item in attachments if item["attachment_id"] == cap["attachment_id"]),
                None,
            )
            if (
                item is None
                or item["file_object_id"] != cap["file_object_id"]
                or item["file_version"] != cap["file_version"]
            ):
                self._invalidate(db, row)
                raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
            if item is None or item["content_type"] not in {"image/jpeg", "image/png"}:
                self._invalidate(db, row)
                raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
            db.execute(
                text(
                    "UPDATE analysis.record_image_capability SET consumed_at=:now WHERE capability_hash=:hash AND consumed_at IS NULL"
                ),
                {"now": now, "hash": digest},
            )
            bucket, object_key, content_type = (
                item["bucket_name"],
                item["object_key"],
                item["content_type"],
            )
        try:
            content = self._storage.read_object_limited(bucket, object_key, 15 * 1024 * 1024)
        except Exception as exc:
            raise Problem(503, "FILE_STORAGE_UNAVAILABLE", "File storage is unavailable") from exc
        if not content or len(content) > 15 * 1024 * 1024:
            raise Problem(409, "TASK_INVALIDATED", "Recognition task is no longer available")
        return content, content_type


def _service(request: Request) -> RecordImageWorkerService:
    service = getattr(request.app.state, "record_image_worker_service", None)
    if service is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Record image worker is unavailable")
    return cast(RecordImageWorkerService, service)


@worker_router.post(
    "/agent/record-image-recognition/claim", operation_id="claimRecordImageRecognitionRequest"
)
def claim_record_image(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    _agent(request, authorization)
    return {"request": _service(request).claim()}


@worker_router.get(
    "/agent/record-image-recognition/requests/{request_id}/input",
    operation_id="getRecordImageRecognitionInput",
)
def get_record_image_input(
    request_id: UUID, request: Request, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    _agent(request, authorization)
    return _service(request).input(request_id)


@worker_router.get(
    "/agent/record-image-recognition/images/{capability}",
    operation_id="readRecordImageRecognitionImage",
)
def read_record_image(
    capability: str, request: Request, authorization: str | None = Header(default=None)
) -> Response:
    _agent(request, authorization)
    content, content_type = _service(request).read_image(capability)
    return Response(content=content, media_type=content_type, headers={"Cache-Control": "no-store"})


@worker_router.post(
    "/agent/record-image-recognition/requests/{request_id}/candidates",
    status_code=204,
    operation_id="submitRecordImageRecognitionCandidates",
)
def submit_record_image_candidates(
    request_id: UUID,
    body: CandidateSubmission,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _agent(request, authorization)
    _service(request).submit_candidates(request_id, body)
    return Response(status_code=204)


@worker_router.post(
    "/agent/record-image-recognition/requests/{request_id}/fail",
    status_code=204,
    operation_id="failRecordImageRecognition",
)
def fail_record_image(
    request_id: UUID,
    body: RecognitionFailure,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _agent(request, authorization)
    _service(request).fail(request_id, body)
    return Response(status_code=204)
