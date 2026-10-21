"""F03/F04 attachment and record-image recognition HTTP surface."""
# ruff: noqa: E501

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.api import current_auth_context
from gutcare.auth.models import PatientConsent, PatientProfile
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")


class AttachBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_object_id: UUID
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)


class RecordImageAttachmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    record_id: UUID
    position: int = Field(ge=0, le=9)
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)
    file_status: Literal["available", "unavailable"]
    created_at: datetime


class DisclosureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: UUID
    purpose: Literal["diet_image_recognition", "stool_image_recognition"]
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)
    policy_version: str = Field(min_length=1, max_length=64)
    acknowledged: Literal[True]


class RecognitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)
    disclosure_token: str = Field(min_length=32, max_length=256)


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "edit", "reject"]
    candidate_version: int = Field(ge=1)
    record_version: int = Field(ge=1)
    image_set_version: int = Field(ge=1)
    corrected_value: (
        Annotated[StrictStr, Field(min_length=1, max_length=160)]
        | Annotated[StrictInt, Field(ge=1, le=7)]
        | None
    ) = None


class DietCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    candidate_version: int
    attachment_id: UUID
    candidate_group_key: UUID
    candidate_type: Literal["food_name", "food_category", "portion_description"]
    value: str | None
    confidence_band: Literal["low", "medium", "high"]
    uncertainty_code: Literal[
        "partially_occluded", "mixed_food", "low_light", "ambiguous_shape", "image_quality", "other"
    ]
    image_region: tuple[float, float, float, float] | None = None
    status: Literal["pending", "accepted", "edited", "rejected", "invalidated"]


class StoolCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    candidate_version: int
    attachment_id: UUID
    candidate_type: Literal["bristol_type"]
    value: int | None
    confidence_band: Literal["low", "medium", "high"]
    uncertainty_code: Literal[
        "partially_occluded", "mixed_food", "low_light", "ambiguous_shape", "image_quality", "other"
    ]
    image_region: tuple[float, float, float, float] | None = None
    status: Literal["pending", "accepted", "edited", "rejected", "invalidated"]


class RecognitionRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    recognition_type: Literal["diet_image_recognition", "stool_image_recognition"]
    status: Literal[
        "pending",
        "processing",
        "candidates_ready",
        "no_candidates",
        "failed",
        "cancelled",
        "invalidated",
    ]
    reason_code: (
        Literal[
            "low_image_quality",
            "unsupported_image",
            "no_visible_food",
            "no_reliable_stool_type",
            "agent_unavailable",
        ]
        | None
    ) = None
    record_version: int
    image_set_version: int
    decision_record_version: int
    attempt: int = Field(ge=1)
    retry_of_request_id: UUID | None
    candidates: list[DietCandidateResponse | StoolCandidateResponse] = Field(max_length=50)
    created_at: datetime
    updated_at: datetime


def _session(request: Request) -> Session:
    record_service = request.app.state.record_service
    if record_service is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    sessions = cast(sessionmaker[Session], record_service._sessions)
    return sessions()


def _patient(db: Session, context: AuthContext) -> UUID:
    db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(context.user_id)})
    profile = db.scalar(
        select(PatientProfile).where(
            PatientProfile.user_id == context.user_id, PatientProfile.deleted_at.is_(None)
        )
    )
    if profile is None:
        raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
    db.execute(text("SELECT set_config('app.patient_id', :pid, true)"), {"pid": str(profile.id)})
    return profile.id


def _consents(db: Session, patient_id: UUID, *, require_ai: bool = False) -> bool:
    latest: dict[str, PatientConsent] = {}
    for row in db.scalars(
        select(PatientConsent)
        .where(PatientConsent.patient_id == patient_id)
        .order_by(PatientConsent.decided_at.desc(), PatientConsent.id.desc())
    ):
        latest.setdefault(row.consent_type, row)
    required = (
        ("health_data_processing", "sensitive_image", "third_party_ai")
        if require_ai
        else ("health_data_processing", "sensitive_image")
    )
    return all(
        (r := latest.get(kind)) is not None and r.granted and r.revoked_at is None
        for kind in required
    )


def _record(
    db: Session, patient_id: UUID, record_id: UUID, record_type: str, *, lock: bool = False
) -> Any:
    table = "diet_record" if record_type == "diet" else "stool_record"
    optional_fields = (
        "meal_type, NULL::smallint AS bristol_type"
        if record_type == "diet"
        else "NULL::text AS meal_type, bristol_type"
    )
    suffix = " FOR UPDATE" if lock else ""
    row = (
        db.execute(
            text(
                f"SELECT id,patient_id,record_version,image_set_version,occurred_at,{optional_fields},deleted_at FROM health.{table} WHERE id=:rid AND patient_id=:pid AND deleted_at IS NULL{suffix}"
            ),
            {"rid": record_id, "pid": patient_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
    return row


def _compact_attachment_positions(
    db: Session, *, table: str, patient_id: UUID, record_id: UUID
) -> None:
    """Close position gaps in ascending order while each target slot is already free."""
    rows = (
        db.execute(
            text(
                f"SELECT id,position FROM health.{table} "
                "WHERE patient_id=:p AND record_id=:r AND deleted_at IS NULL "
                "ORDER BY position,id FOR UPDATE"
            ),
            {"p": patient_id, "r": record_id},
        )
        .mappings()
        .all()
    )
    for position, row in enumerate(rows):
        if row["position"] == position:
            continue
        db.execute(
            text(
                f"UPDATE health.{table} SET position=:position "
                "WHERE id=:id AND patient_id=:p AND record_id=:r AND deleted_at IS NULL"
            ),
            {"position": position, "id": row["id"], "p": patient_id, "r": record_id},
        )


def _attach(record_type: str, operation: str) -> Callable[..., dict[str, Any]]:
    table = "diet_record_image" if record_type == "diet" else "stool_record_image"
    record_table = "diet_record" if record_type == "diet" else "stool_record"
    expected = f"{record_type}_image"

    def endpoint(
        record_id: UUID,
        body: AttachBody,
        request: Request,
        context: Annotated[AuthContext, Depends(current_auth_context)],
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    ) -> dict[str, Any]:
        db = _session(request)
        try:
            with db.begin():
                patient_id = _patient(db, context)
                db.execute(
                    text(
                        "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                    ),
                    {"p": str(patient_id)},
                )
                rec = _record(db, patient_id, record_id, record_type, lock=True)
                if not _consents(db, patient_id):
                    raise Problem(409, "CONSENT_REQUIRED", "Required image consent is missing")
                digest = hashlib.sha256(
                    json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
                ).hexdigest()
                idem = (
                    db.execute(
                        text(
                            "SELECT request_hash,resource_id FROM health.record_image_idempotency WHERE patient_id=:p AND operation=:o AND idempotency_key=:k FOR UPDATE"
                        ),
                        {"p": patient_id, "o": operation, "k": key},
                    )
                    .mappings()
                    .first()
                )
                if idem:
                    if idem["request_hash"] != digest:
                        raise Problem(
                            409,
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key was used with a different request",
                        )
                    current = (
                        db.execute(
                            text(
                                f"SELECT a.id,a.record_id,a.position,a.created_at, "
                                "CASE WHEN f.storage_status='available' AND f.scan_status='clean' AND f.deleted_at IS NULL "
                                "THEN 'available' ELSE 'unavailable' END AS file_status "
                                f"FROM health.{table} a JOIN health.file_object f ON f.id=a.file_object_id AND f.patient_id=a.patient_id "
                                "WHERE a.id=:id AND a.patient_id=:p AND a.deleted_at IS NULL"
                            ),
                            {"id": idem["resource_id"], "p": patient_id},
                        )
                        .mappings()
                        .first()
                    )
                    if current:
                        return {
                            **dict(current),
                            "record_version": rec["record_version"],
                            "image_set_version": rec["image_set_version"],
                        }
                if (
                    rec["record_version"] != body.record_version
                    or rec["image_set_version"] != body.image_set_version
                ):
                    raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
                file = db.execute(
                    text("""SELECT f.id FROM health.file_object f
                        JOIN health.upload_session u ON u.file_object_id=f.id AND u.patient_id=f.patient_id
                        WHERE f.id=:file_id AND f.patient_id=:patient_id AND u.purpose=:purpose
                          AND u.status='completed' AND f.scan_status='clean'
                          AND f.storage_status='available' AND f.deleted_at IS NULL"""),
                    {"file_id": body.file_object_id, "patient_id": patient_id, "purpose": expected},
                ).first()
                if file is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                count: int = int(
                    db.execute(
                        text(
                            f"SELECT count(*) FROM health.{table} WHERE patient_id=:p AND record_id=:r AND deleted_at IS NULL"
                        ),
                        {"p": patient_id, "r": record_id},
                    ).scalar_one()
                )
                limit = 10 if record_type == "diet" else 1
                if count >= limit:
                    raise Problem(409, "ATTACHMENT_LIMIT_REACHED", "Attachment limit reached")
                position = int(count) if record_type == "diet" else 0
                row = (
                    db.execute(
                        text(
                            f"INSERT INTO health.{table}(patient_id,record_id,file_object_id,position) VALUES (:p,:r,:f,:pos) RETURNING id,record_id,position,created_at"
                        ),
                        {
                            "p": patient_id,
                            "r": record_id,
                            "f": body.file_object_id,
                            "pos": position,
                        },
                    )
                    .mappings()
                    .one()
                )
                db.execute(
                    text(
                        f"UPDATE health.{record_table} SET record_version=record_version+1,image_set_version=image_set_version+1,updated_at=now() WHERE id=:r AND patient_id=:p"
                    ),
                    {"r": record_id, "p": patient_id},
                )
                db.execute(
                    text(
                        "INSERT INTO health.record_image_idempotency(patient_id,operation,idempotency_key,request_hash,resource_id) VALUES (:p,:o,:k,:h,:id)"
                    ),
                    {"p": patient_id, "o": operation, "k": key, "h": digest, "id": row["id"]},
                )
                db.execute(
                    text("SELECT set_config('app.patient_id', :pid, true)"),
                    {"pid": str(patient_id)},
                )
                return {
                    "id": str(row["id"]),
                    "record_id": str(row["record_id"]),
                    "position": row["position"],
                    "file_status": "available",
                    "created_at": row["created_at"].isoformat(),
                    "record_version": rec["record_version"] + 1,
                    "image_set_version": rec["image_set_version"] + 1,
                }
        finally:
            db.close()

    return endpoint


def _list_images(record_type: str) -> Callable[..., list[dict[str, Any]]]:
    table = "diet_record_image" if record_type == "diet" else "stool_record_image"

    def endpoint(
        record_id: UUID,
        request: Request,
        context: Annotated[AuthContext, Depends(current_auth_context)],
    ) -> list[dict[str, Any]]:
        db = _session(request)
        try:
            patient_id = _patient(db, context)
            rec = _record(db, patient_id, record_id, record_type)
            rows = db.execute(
                text(
                    f"SELECT a.id,a.record_id,a.position,a.created_at, "
                    "CASE WHEN f.storage_status='available' AND f.scan_status='clean' AND f.deleted_at IS NULL "
                    "THEN 'available' ELSE 'unavailable' END AS file_status "
                    f"FROM health.{table} a JOIN health.file_object f ON f.id=a.file_object_id AND f.patient_id=a.patient_id "
                    "WHERE a.patient_id=:p AND a.record_id=:r AND a.deleted_at IS NULL ORDER BY a.position"
                ),
                {"p": patient_id, "r": record_id},
            ).mappings()
            return [
                {
                    "id": str(r["id"]),
                    "record_id": str(r["record_id"]),
                    "position": r["position"],
                    "record_version": rec["record_version"],
                    "image_set_version": rec["image_set_version"],
                    "file_status": r["file_status"],
                    "created_at": r["created_at"].isoformat(),
                }
                for r in rows
            ]
        finally:
            db.close()

    return endpoint


@router.get(
    "/dietary-records/{record_id}/images",
    operation_id="listDietRecordImages",
    tags=["Records"],
    response_model=list[RecordImageAttachmentResponse],
)
def list_diet_images(
    record_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> list[dict[str, Any]]:
    return _list_images("diet")(record_id, request, context)


@router.post(
    "/dietary-records/{record_id}/images",
    status_code=201,
    operation_id="attachDietRecordImage",
    tags=["Records"],
    response_model=RecordImageAttachmentResponse,
)
def attach_diet_image(
    record_id: UUID,
    body: AttachBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return _attach("diet", "diet_image_attach")(record_id, body, request, context, key)


@router.get(
    "/stool-records/{record_id}/images",
    operation_id="listStoolRecordImages",
    tags=["Records"],
    response_model=list[RecordImageAttachmentResponse],
)
def list_stool_images(
    record_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> list[dict[str, Any]]:
    return _list_images("stool")(record_id, request, context)


@router.post(
    "/stool-records/{record_id}/images",
    status_code=201,
    operation_id="attachStoolRecordImage",
    tags=["Records"],
    response_model=RecordImageAttachmentResponse,
)
def attach_stool_image(
    record_id: UUID,
    body: AttachBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return _attach("stool", "stool_image_attach")(record_id, body, request, context, key)


@router.delete(
    "/record-images/{image_id}",
    status_code=204,
    operation_id="deleteRecordImage",
    tags=["Records"],
)
def delete_record_image(
    image_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    record_version: int = Query(ge=1),
    image_set_version: int = Query(ge=1),
) -> Response:
    db = _session(request)
    try:
        with db.begin():
            patient_id = _patient(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                ),
                {"p": str(patient_id)},
            )
            found = None
            kind = "diet"
            table = "diet_record_image"
            record_table = "diet_record"
            for candidate_kind, candidate_table, candidate_record_table in (
                ("diet", "diet_record_image", "diet_record"),
                ("stool", "stool_record_image", "stool_record"),
            ):
                found = (
                    db.execute(
                        text(
                            f"SELECT id,record_id,file_object_id FROM health.{candidate_table} WHERE id=:id AND patient_id=:p AND deleted_at IS NULL"
                        ),
                        {"id": image_id, "p": patient_id},
                    )
                    .mappings()
                    .first()
                )
                if found is not None:
                    kind = candidate_kind
                    table = candidate_table
                    record_table = candidate_record_table
                    break
            if found is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            rec = _record(db, patient_id, found["record_id"], kind, lock=True)
            if (
                rec["record_version"] != record_version
                or rec["image_set_version"] != image_set_version
            ):
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            db.execute(
                text(f"UPDATE health.{table} SET deleted_at=now() WHERE id=:id AND patient_id=:p"),
                {"id": image_id, "p": patient_id},
            )
            _compact_attachment_positions(
                db, table=table, patient_id=patient_id, record_id=found["record_id"]
            )
            db.execute(
                text(
                    "UPDATE analysis.record_image_recognition_request SET status='invalidated',updated_at=now() WHERE patient_id=:p AND record_id=:r AND status IN ('pending','processing','candidates_ready')"
                ),
                {"p": patient_id, "r": found["record_id"]},
            )
            db.execute(
                text(
                    "UPDATE analysis.record_image_candidate SET status='invalidated',value='null'::jsonb,locator=NULL WHERE patient_id=:p AND request_id IN (SELECT id FROM analysis.record_image_recognition_request WHERE patient_id=:p AND record_id=:r AND status='invalidated') AND status='pending'"
                ),
                {"p": patient_id, "r": found["record_id"]},
            )
            db.execute(
                text(
                    "DELETE FROM analysis.record_image_capability WHERE patient_id=:p AND request_id IN (SELECT id FROM analysis.record_image_recognition_request WHERE patient_id=:p AND record_id=:r AND status='invalidated')"
                ),
                {"p": patient_id, "r": found["record_id"]},
            )
            db.execute(
                text(
                    "UPDATE health."
                    + record_table
                    + " SET record_version=record_version+1,image_set_version=image_set_version+1,updated_at=now() WHERE id=:r AND patient_id=:p"
                ),
                {"r": found["record_id"], "p": patient_id},
            )
            db.execute(
                text(
                    "UPDATE health.file_object SET deleted_at=now(),storage_status='deleting' WHERE id=:id AND patient_id=:p"
                ),
                {"id": found["file_object_id"], "p": patient_id},
            )
            db.execute(
                text(
                    "INSERT INTO integration.file_deletion_job(patient_id,file_object_id,bucket_name,object_key,due_at) SELECT patient_id,id,bucket_name,object_key,now()+interval '7 days' FROM health.file_object WHERE id=:id AND patient_id=:p ON CONFLICT(file_object_id) DO NOTHING"
                ),
                {"id": found["file_object_id"], "p": patient_id},
            )
        return Response(status_code=204)
    finally:
        db.close()


def _recognition_request_dto(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "recognition_type": row["recognition_type"],
        "status": row["status"],
        "record_version": row["record_version"],
        "image_set_version": row["image_set_version"],
        "decision_record_version": row["decision_record_version"],
        "attempt": row["attempt"],
        "retry_of_request_id": (
            str(row["retry_of_request_id"]) if row["retry_of_request_id"] else None
        ),
        "reason_code": {
            "invalid_image": "unsupported_image",
            "timeout": "agent_unavailable",
            "internal_processing_error": "agent_unavailable",
            "agent_unavailable": "agent_unavailable",
        }.get(row["failure_code"]),
        "candidates": [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get(
    "/record-image-recognition-disclosures",
    operation_id="getRecordImageRecognitionDisclosure",
    tags=["Records"],
)
def get_disclosure(
    purpose: Literal["diet_image_recognition", "stool_image_recognition"],
    request: Request,
    _: Annotated[AuthContext, Depends(current_auth_context)],
) -> dict[str, Any]:
    path = request.app.state.settings.record_image_disclosures_path
    if path is None:
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[4]
            / "contracts"
            / "consent"
            / "record-image-recognition-notices.json"
        )
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        item = next(x for x in artifact["purpose_disclosures"] if x["purpose"] == purpose)
    except (OSError, ValueError, KeyError, StopIteration):
        return {"purpose": purpose, "enabled": False}
    # Production stays closed until the artifact carries formal approval and exact runtime configuration.
    settings = request.app.state.settings
    prefix = "diet" if purpose.startswith("diet_") else "stool"
    enabled = (
        settings.env in {"test", "local"}
        and artifact.get("artifact_classification") == "development_test_only"
        and getattr(settings, f"{prefix}_image_recognition_policy_version")
        == item.get("policy_version")
        and str(getattr(settings, f"{prefix}_image_recognition_summary_hash") or "").lower()
        == str(item.get("summary_sha256", "")).lower()
    )
    return {**item, "enabled": bool(enabled and item.get("enabled"))}


@router.post(
    "/record-image-recognition-disclosures",
    status_code=201,
    operation_id="acknowledgeRecordImageRecognitionDisclosure",
    tags=["Records"],
)
def acknowledge_disclosure(
    body: DisclosureBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> dict[str, Any]:
    db = _session(request)
    token = secrets.token_urlsafe(48)
    try:
        with db.begin():
            patient_id = _patient(db, context)
            record_type = "diet" if body.purpose.startswith("diet_") else "stool"
            rec = _record(db, patient_id, body.record_id, record_type, lock=True)
            if (
                rec["record_version"] != body.record_version
                or rec["image_set_version"] != body.image_set_version
            ):
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            if not _consents(db, patient_id, require_ai=True):
                raise Problem(
                    409, "CONSENT_REQUIRED", "Required image recognition consent is missing"
                )
            notice_response = get_disclosure(body.purpose, request, context)
            if not notice_response.get("enabled") or body.policy_version != notice_response.get(
                "policy_version"
            ):
                raise Problem(
                    503, "DISCLOSURE_UNAVAILABLE", "Recognition disclosure is unavailable"
                )
            summary_hash = notice_response["summary_sha256"]
            db.execute(
                text(
                    "INSERT INTO health.record_image_disclosure(patient_id,record_id,purpose,record_version,image_set_version,policy_version,summary_sha256,token_hash,expires_at) VALUES (:p,:r,:u,:rv,:iv,:pv,:sh,:th,:exp)"
                ),
                {
                    "p": patient_id,
                    "r": body.record_id,
                    "u": body.purpose,
                    "rv": body.record_version,
                    "iv": body.image_set_version,
                    "pv": body.policy_version,
                    "sh": summary_hash,
                    "th": hashlib.sha256(token.encode()).hexdigest(),
                    "exp": datetime.now(UTC) + timedelta(minutes=5),
                },
            )
        return {
            "token": token,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "purpose": body.purpose,
            "policy_version": body.policy_version,
        }
    finally:
        db.close()


@router.post(
    "/dietary-records/{record_id}/image-recognition-requests",
    status_code=202,
    response_model=RecognitionRequestResponse,
    operation_id="createDietImageRecognitionRequest",
    tags=["Records"],
)
def create_diet_recognition(
    record_id: UUID,
    body: RecognitionBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return _create_recognition("diet", record_id, body, request, context, key)


@router.post(
    "/stool-records/{record_id}/image-recognition-requests",
    status_code=202,
    response_model=RecognitionRequestResponse,
    operation_id="createStoolImageRecognitionRequest",
    tags=["Records"],
)
def create_stool_recognition(
    record_id: UUID,
    body: RecognitionBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return _create_recognition("stool", record_id, body, request, context, key)


@router.post(
    "/record-image-recognition-requests/{request_id}/retry",
    status_code=202,
    response_model=RecognitionRequestResponse,
    operation_id="retryRecordImageRecognitionRequest",
    tags=["Records"],
)
def retry_record_image_recognition(
    request_id: UUID,
    body: RecognitionBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return _create_recognition(
        None, None, body, request, context, key, parent_request_id=request_id
    )


@router.get(
    "/record-image-recognition-requests/{request_id}",
    response_model=RecognitionRequestResponse,
    operation_id="getRecordImageRecognitionRequest",
    tags=["Records"],
)
def get_recognition_request(
    request_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
) -> dict[str, Any]:
    db = _session(request)
    try:
        patient_id = _patient(db, context)
        row = (
            db.execute(
                text("""SELECT id,recognition_type,status,record_version,
                decision_record_version,image_set_version,attempt,retry_of_request_id,
                failure_code,created_at,updated_at
                FROM analysis.record_image_recognition_request
                WHERE id=:id AND patient_id=:patient_id"""),
                {"id": request_id, "patient_id": patient_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        candidates = db.execute(
            text("""SELECT id,attachment_id,candidate_type,candidate_group_key,confidence_band,value,locator,uncertainty,
                candidate_version,status FROM analysis.record_image_candidate
                WHERE request_id=:id AND patient_id=:patient_id ORDER BY created_at,id"""),
            {"id": request_id, "patient_id": patient_id},
        ).mappings()
        return {
            "id": str(row["id"]),
            "recognition_type": row["recognition_type"],
            "status": row["status"],
            "record_version": row["record_version"],
            "image_set_version": row["image_set_version"],
            "decision_record_version": row["decision_record_version"],
            "attempt": row["attempt"],
            "retry_of_request_id": (
                str(row["retry_of_request_id"]) if row["retry_of_request_id"] else None
            ),
            "reason_code": {
                "invalid_image": "unsupported_image",
                "timeout": "agent_unavailable",
                "internal_processing_error": "agent_unavailable",
                "agent_unavailable": "agent_unavailable",
            }.get(row["failure_code"]),
            "candidates": [
                {
                    "id": str(candidate["id"]),
                    "attachment_id": str(candidate["attachment_id"]),
                    "candidate_type": candidate["candidate_type"],
                    **(
                        {"candidate_group_key": str(candidate["candidate_group_key"])}
                        if row["recognition_type"] == "diet_image_recognition"
                        else {}
                    ),
                    "value": candidate["value"],
                    "confidence_band": candidate["confidence_band"],
                    "image_region": candidate["locator"],
                    "uncertainty_code": candidate["uncertainty"],
                    "candidate_version": candidate["candidate_version"],
                    "status": candidate["status"],
                }
                for candidate in candidates
            ],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        db.close()


@router.post(
    "/record-image-candidates/{candidate_id}/decision",
    status_code=204,
    operation_id="decideRecordImageCandidate",
    tags=["Records"],
)
def decide_record_image_candidate(
    candidate_id: UUID,
    body: DecisionBody,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> Response:
    db = _session(request)
    try:
        with db.begin():
            patient_id = _patient(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                ),
                {"p": str(patient_id)},
            )
            probe = (
                db.execute(
                    text(
                        "SELECT c.request_id,r.record_id,r.recognition_type FROM analysis.record_image_candidate c JOIN analysis.record_image_recognition_request r ON r.id=c.request_id AND r.patient_id=c.patient_id WHERE c.id=:id AND c.patient_id=:patient_id"
                    ),
                    {"id": candidate_id, "patient_id": patient_id},
                )
                .mappings()
                .first()
            )
            if probe is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            kind = "diet" if probe["recognition_type"] == "diet_image_recognition" else "stool"
            rec = _record(db, patient_id, probe["record_id"], kind, lock=True)
            request_row = (
                db.execute(
                    text(
                        "SELECT id,record_id,disclosure_id,recognition_type,record_version,decision_record_version,image_set_version,status FROM analysis.record_image_recognition_request WHERE id=:id AND patient_id=:patient_id FOR UPDATE"
                    ),
                    {"id": probe["request_id"], "patient_id": patient_id},
                )
                .mappings()
                .first()
            )
            if request_row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            candidate = (
                db.execute(
                    text(
                        "SELECT candidate_type,candidate_group_key,attachment_id,value,candidate_version,status,uncertainty,source_state FROM analysis.record_image_candidate WHERE id=:id AND patient_id=:patient_id FOR UPDATE"
                    ),
                    {"id": candidate_id, "patient_id": patient_id},
                )
                .mappings()
                .first()
            )
            if candidate is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            digest = hashlib.sha256(
                json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
            if not _consents(db, patient_id, require_ai=True):
                raise Problem(
                    409, "CONSENT_REQUIRED", "Required image recognition consent is missing"
                )
            if not db.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM health.record_image_disclosure WHERE id=:id AND patient_id=:p AND record_id=:r AND purpose=:purpose AND consumed_at IS NOT NULL)"
                ),
                {
                    "id": request_row["disclosure_id"],
                    "p": patient_id,
                    "r": request_row["record_id"],
                    "purpose": request_row["recognition_type"],
                },
            ):
                raise Problem(
                    409, "DISCLOSURE_REQUIRED", "Purpose-specific disclosure is unavailable"
                )
            idem = db.execute(
                text(
                    "SELECT request_hash FROM health.record_image_idempotency WHERE patient_id=:p AND operation='candidate_decision' AND idempotency_key=:k FOR UPDATE"
                ),
                {"p": patient_id, "k": key},
            ).first()
            if idem is not None:
                if idem[0] != digest:
                    raise Problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key was used with a different request",
                    )
                return Response(status_code=204)
            if (
                candidate["status"] != "pending"
                or candidate["source_state"] != "current"
                or request_row["status"] != "candidates_ready"
            ):
                raise Problem(409, "CANDIDATE_UNAVAILABLE", "Candidate is no longer available")
            if (
                candidate["candidate_version"] != body.candidate_version
                or rec["record_version"] != body.record_version
                or request_row["decision_record_version"] != body.record_version
                or rec["image_set_version"] != body.image_set_version
                or request_row["image_set_version"] != body.image_set_version
            ):
                raise Problem(
                    409, "RECORD_VERSION_CONFLICT", "Record or candidate version has changed"
                )
            if (body.action == "edit") != (body.corrected_value is not None):
                raise Problem(
                    422, "VALIDATION_ERROR", "Edited candidate value is required only for edit"
                )
            value = body.corrected_value if body.action == "edit" else candidate["value"]
            candidate_type = candidate["candidate_type"]
            group_key = candidate["candidate_group_key"]
            if kind == "diet":
                if group_key is None or candidate_type not in {
                    "food_name",
                    "food_category",
                    "portion_description",
                }:
                    raise Problem(422, "VALIDATION_ERROR", "Diet candidate type is unsupported")
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
                    raise Problem(
                        422, "VALIDATION_ERROR", "Diet candidate value must be bounded text"
                    )
                value = value.strip()
                if candidate_type == "food_category" and value not in {
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
            elif (
                group_key is not None
                or candidate_type != "bristol_type"
                or isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 7
            ):
                raise Problem(
                    422, "VALIDATION_ERROR", "Bristol type must be an integer from 1 to 7"
                )
            if (
                kind == "diet"
                and body.action in {"accept", "edit"}
                and candidate_type != "food_name"
            ):
                existing_item = db.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM health.diet_item WHERE patient_id=:p AND diet_record_id=:r AND source_recognition_request_id=:request AND source_candidate_group_key=:group)"
                    ),
                    {
                        "p": patient_id,
                        "r": request_row["record_id"],
                        "request": request_row["id"],
                        "group": group_key,
                    },
                )
                if not existing_item:
                    raise Problem(
                        409,
                        "candidate_dependency_unmet",
                        "Candidate dependency unmet",
                        "Confirm or edit this group's food_name first.",
                    )
            db.execute(
                text(
                    "INSERT INTO analysis.record_image_decision(patient_id,request_id,candidate_id,action,candidate_type) VALUES (:p,:r,:c,:a,:t)"
                ),
                {
                    "p": patient_id,
                    "r": request_row["id"],
                    "c": candidate_id,
                    "a": body.action,
                    "t": candidate["candidate_type"],
                },
            )
            db.execute(
                text(
                    "UPDATE analysis.record_image_candidate SET status=:status,value='null'::jsonb,locator=NULL WHERE id=:id AND patient_id=:p"
                ),
                {
                    "status": {"accept": "accepted", "edit": "edited", "reject": "rejected"}[
                        body.action
                    ],
                    "id": candidate_id,
                    "p": patient_id,
                },
            )
            if body.action in {"accept", "edit"}:
                # Only patient-confirmed structured facts are written; no risk inference occurs here.
                if kind == "stool" and candidate["candidate_type"] == "bristol_type":
                    db.execute(
                        text(
                            "UPDATE health.stool_record SET bristol_type=:value,record_version=record_version+1,updated_at=now() WHERE id=:r AND patient_id=:p"
                        ),
                        {"value": value, "r": request_row["record_id"], "p": patient_id},
                    )
                elif kind == "diet" and candidate["candidate_type"] == "food_name":
                    position = db.scalar(
                        text(
                            "SELECT COALESCE(MAX(item_position),-1)+1 FROM health.diet_item WHERE patient_id=:p AND diet_record_id=:r"
                        ),
                        {"p": patient_id, "r": request_row["record_id"]},
                    )
                    db.execute(
                        text(
                            "INSERT INTO health.diet_item(diet_record_id,patient_id,name,item_position,source_recognition_request_id,source_candidate_group_key,source_type,confirmed_by_patient) VALUES (:r,:p,:name,:position,:request,:group,'patient_confirmed_image',true)"
                        ),
                        {
                            "r": request_row["record_id"],
                            "p": patient_id,
                            "name": value,
                            "position": position,
                            "request": request_row["id"],
                            "group": group_key,
                        },
                    )
                elif kind == "diet" and candidate["candidate_type"] in {
                    "food_category",
                    "portion_description",
                }:
                    field = (
                        "category_code"
                        if candidate["candidate_type"] == "food_category"
                        else "amount_text"
                    )
                    db.execute(
                        text(
                            f"UPDATE health.diet_item SET {field}=:value WHERE patient_id=:p AND diet_record_id=:r AND source_recognition_request_id=:request AND source_candidate_group_key=:group"
                        ),
                        {
                            "value": value,
                            "p": patient_id,
                            "r": request_row["record_id"],
                            "request": request_row["id"],
                            "group": group_key,
                        },
                    )
                db.execute(
                    text(
                        "UPDATE health."
                        + ("diet_record" if kind == "diet" else "stool_record")
                        + " SET record_version=record_version+1,updated_at=now() WHERE id=:r AND patient_id=:p"
                    ),
                    {"r": request_row["record_id"], "p": patient_id},
                )
                db.execute(
                    text(
                        "UPDATE analysis.record_image_recognition_request SET decision_record_version=decision_record_version+1,updated_at=now() WHERE id=:r AND patient_id=:p"
                    ),
                    {"r": request_row["id"], "p": patient_id},
                )
            if (
                kind == "diet"
                and candidate["candidate_type"] == "food_name"
                and body.action == "reject"
            ):
                db.execute(
                    text(
                        "UPDATE analysis.record_image_candidate SET status='invalidated',value='null'::jsonb,locator=NULL WHERE request_id=:r AND patient_id=:p AND candidate_group_key=:g AND candidate_type IN ('food_category','portion_description') AND status='pending'"
                    ),
                    {"r": request_row["id"], "p": patient_id, "g": group_key},
                )
            db.execute(
                text(
                    "INSERT INTO health.record_image_idempotency(patient_id,operation,idempotency_key,request_hash,resource_id) VALUES (:p,'candidate_decision',:k,:h,:id)"
                ),
                {"p": patient_id, "k": key, "h": digest, "id": candidate_id},
            )
        return Response(status_code=204)
    finally:
        db.close()


def _create_recognition(
    kind: str | None,
    record_id: UUID | None,
    body: RecognitionBody,
    request: Request,
    context: AuthContext,
    key: str,
    *,
    parent_request_id: UUID | None = None,
) -> dict[str, Any]:
    db = _session(request)
    try:
        with db.begin():
            patient_id = _patient(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                ),
                {"p": str(patient_id)},
            )
            parent = None
            if parent_request_id is not None:
                parent = (
                    db.execute(
                        text("""SELECT id,record_id,recognition_type,status,attempt
                        FROM analysis.record_image_recognition_request
                        WHERE id=:id AND patient_id=:p"""),
                        {"id": parent_request_id, "p": patient_id},
                    )
                    .mappings()
                    .first()
                )
                if parent is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                kind = "diet" if parent["recognition_type"] == "diet_image_recognition" else "stool"
                record_id = parent["record_id"]
            assert kind is not None and record_id is not None
            rec = _record(db, patient_id, record_id, kind, lock=True)
            if parent is not None:
                parent = (
                    db.execute(
                        text("""SELECT id,record_id,recognition_type,status,attempt
                        FROM analysis.record_image_recognition_request
                        WHERE id=:id AND patient_id=:p FOR UPDATE"""),
                        {"id": parent_request_id, "p": patient_id},
                    )
                    .mappings()
                    .first()
                )
                if parent is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            operation = f"{kind}_recognition_create" if parent is None else "recognition_retry"
            scope_id = None if parent is None else parent["id"]
            if not _consents(db, patient_id, require_ai=True):
                raise Problem(
                    409, "CONSENT_REQUIRED", "Required image recognition consent is missing"
                )
            digest = hashlib.sha256(
                json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
            idem = (
                db.execute(
                    text("""SELECT request_hash,resource_id FROM health.record_image_idempotency
                    WHERE patient_id=:p AND operation=:o AND scope_id IS NOT DISTINCT FROM :scope
                      AND idempotency_key=:k FOR UPDATE"""),
                    {"p": patient_id, "o": operation, "scope": scope_id, "k": key},
                )
                .mappings()
                .first()
            )
            if idem is not None:
                if idem["request_hash"] != digest:
                    raise Problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key was used with a different request",
                    )
                prior = (
                    db.execute(
                        text("""SELECT id,recognition_type,status,record_version,
                        decision_record_version,image_set_version,attempt,retry_of_request_id,
                        failure_code,created_at,updated_at
                        FROM analysis.record_image_recognition_request
                        WHERE id=:id AND patient_id=:p"""),
                        {"id": idem["resource_id"], "p": patient_id},
                    )
                    .mappings()
                    .first()
                )
                if prior is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                return _recognition_request_dto(prior)
            if (
                rec["record_version"] != body.record_version
                or rec["image_set_version"] != body.image_set_version
            ):
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            if parent is not None:
                if parent["status"] not in {"failed", "cancelled", "invalidated"}:
                    raise Problem(
                        409,
                        "RECORD_IMAGE_RETRY_NOT_ALLOWED",
                        "Recognition request is not retryable",
                    )
                if db.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM analysis.record_image_recognition_request WHERE retry_of_request_id=:id)"
                    ),
                    {"id": parent["id"]},
                ):
                    raise Problem(
                        409,
                        "RECORD_IMAGE_RETRY_NOT_ALLOWED",
                        "Recognition request already has a retry",
                    )
            if db.scalar(
                text("""SELECT EXISTS(SELECT 1 FROM analysis.record_image_recognition_request
                WHERE patient_id=:p AND record_id=:r
                  AND status IN ('pending','processing','candidates_ready'))"""),
                {"p": patient_id, "r": record_id},
            ):
                raise Problem(
                    409,
                    "RECORD_IMAGE_RETRY_NOT_ALLOWED"
                    if parent is not None
                    else "RECORD_IMAGE_REQUEST_ACTIVE",
                    "A recognition request is already active for this record",
                )
            token_hash = hashlib.sha256(body.disclosure_token.encode()).hexdigest()
            disclosure = db.execute(
                text(
                    "SELECT id FROM health.record_image_disclosure WHERE patient_id=:p AND record_id=:r AND record_version=:rv AND image_set_version=:iv AND purpose=:purpose AND token_hash=:th AND expires_at>now() AND consumed_at IS NULL FOR UPDATE"
                ),
                {
                    "p": patient_id,
                    "r": record_id,
                    "rv": body.record_version,
                    "iv": body.image_set_version,
                    "purpose": f"{kind}_image_recognition",
                    "th": token_hash,
                },
            ).first()
            if disclosure is None:
                raise Problem(
                    409, "DISCLOSURE_TOKEN_INVALID", "Disclosure confirmation is invalid or expired"
                )
            table = "diet_record_image" if kind == "diet" else "stool_record_image"
            attachments = list(
                db.execute(
                    text(
                        f"SELECT a.id AS attachment_id,a.file_object_id,1 AS file_version,f.content_type FROM health.{table} a JOIN health.file_object f ON f.id=a.file_object_id AND f.patient_id=a.patient_id WHERE a.patient_id=:p AND a.record_id=:r AND a.deleted_at IS NULL AND f.storage_status='available' AND f.scan_status='clean' ORDER BY a.position"
                    ),
                    {"p": patient_id, "r": record_id},
                ).mappings()
            )
            if not attachments:
                raise Problem(
                    409, "ATTACHMENT_REQUIRED", "At least one available image is required"
                )
            row = (
                db.execute(
                    text(
                        "INSERT INTO analysis.record_image_recognition_request(patient_id,record_id,disclosure_id,recognition_type,record_version,decision_record_version,image_set_version,attempt,retry_of_request_id) VALUES (:p,:r,:disclosure,:type,:rv,:rv,:iv,:attempt,:parent) RETURNING id,status,record_version,decision_record_version,image_set_version,attempt,retry_of_request_id,created_at,updated_at"
                    ),
                    {
                        "p": patient_id,
                        "r": record_id,
                        "type": f"{kind}_image_recognition",
                        "disclosure": disclosure[0],
                        "rv": body.record_version,
                        "iv": body.image_set_version,
                        "attempt": 1 if parent is None else int(parent["attempt"]) + 1,
                        "parent": None if parent is None else parent["id"],
                    },
                )
                .mappings()
                .one()
            )
            for position, attachment in enumerate(attachments):
                db.execute(
                    text("""INSERT INTO analysis.record_image_request_attachment(
                    request_id,patient_id,position,file_version,diet_attachment_id,stool_attachment_id
                    ) VALUES (:request,:patient,:position,:file_version,:diet_attachment,:stool_attachment)"""),
                    {
                        "request": row["id"],
                        "patient": patient_id,
                        "position": position,
                        "file_version": attachment["file_version"],
                        "diet_attachment": attachment["attachment_id"] if kind == "diet" else None,
                        "stool_attachment": attachment["attachment_id"]
                        if kind == "stool"
                        else None,
                    },
                )
            db.execute(
                text(
                    "INSERT INTO health.record_image_idempotency"
                    "(patient_id,operation,scope_id,idempotency_key,request_hash,resource_id) "
                    "VALUES (:p,:o,:scope,:k,:h,:id)"
                ),
                {
                    "p": patient_id,
                    "o": operation,
                    "scope": scope_id,
                    "k": key,
                    "h": digest,
                    "id": row["id"],
                },
            )
            db.execute(
                text("UPDATE health.record_image_disclosure SET consumed_at=now() WHERE id=:id"),
                {"id": disclosure[0]},
            )
        return {
            "id": str(row["id"]),
            "recognition_type": f"{kind}_image_recognition",
            "status": row["status"],
            "record_version": body.record_version,
            "image_set_version": body.image_set_version,
            "decision_record_version": row["decision_record_version"],
            "attempt": row["attempt"],
            "retry_of_request_id": (
                str(row["retry_of_request_id"]) if row["retry_of_request_id"] else None
            ),
            "reason_code": None,
            "candidates": [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        db.close()
