"""F09 strict advice callback and patient lifecycle API."""

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from sqlalchemy import desc, select, text, tuple_
from sqlalchemy.orm import Session, sessionmaker

from gutcare.analysis.advice_models import (
    AdviceCallback,
    AdviceEvidence,
    AdviceFeedback,
    AdviceFeedbackEvent,
    HealthAdvice,
)
from gutcare.analysis.models import AnalysisTask, TaskInputSnapshot
from gutcare.analysis.service import AnalysisService
from gutcare.auth.api import current_auth_context, problem_response
from gutcare.auth.models import PatientConsent, PatientProfile, UserAccount
from gutcare.auth.service import AuthContext
from gutcare.files.models import ConfirmedMedicalFact, MedicalFieldCandidate
from gutcare.medication.models import MedicationCheckin, MedicationPlan
from gutcare.mood.models import MoodRecord
from gutcare.records.models import DietRecord, RiskAlert, StoolRecord, SymptomRecord
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1/advice", tags=["Advice"])
agent_router = APIRouter(prefix="/internal/v1/agent/advice", tags=["Agent Advice"])


class PatientEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_type: Literal["patient"]
    source_type: Literal[
        "confirmed_medical_fact",
        "diet_record",
        "stool_record",
        "symptom_record",
        "mood_record",
        "medication_plan",
        "medication_checkin",
        "risk_alert",
    ]
    source_id: UUID
    source_version: int = Field(strict=True, ge=1)
    locator: str = Field(min_length=1, max_length=160)


class KnowledgeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_type: Literal["knowledge"]
    knowledge_ref: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:/-]+$")
    knowledge_version: str = Field(min_length=1, max_length=64)
    knowledge_title: str = Field(min_length=1, max_length=240)
    knowledge_publisher: str = Field(min_length=1, max_length=160)
    citation_url: AnyHttpUrl | None = None


class AdviceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal[
        "diet", "lifestyle", "record_management", "medication_adherence", "care_consultation"
    ]
    priority: Literal["routine", "important"]
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=3000)
    uncertainty: "Uncertainty"
    applicability: "Applicability"
    safety_boundary: "SafetyBoundary"
    version: str = Field(min_length=1, max_length=32)
    evidence: list[PatientEvidence | KnowledgeEvidence] = Field(min_length=1, max_length=30)


class Uncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["low", "moderate", "high"]
    reasons: list[Annotated[str, Field(max_length=240)]] = Field(max_length=10)


class Applicability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["general", "condition_specific"]
    limitations: list[Annotated[str, Field(max_length=240)]] = Field(max_length=10)


class SafetyBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_diagnosis: Literal[True]
    not_prescription: Literal[True]
    risk_alert_priority: Literal[True]


AdviceItem.model_rebuild()


def _snapshot_has_explicit_diagnosis(records: list[dict[str, Any]]) -> bool:
    return any(
        record.get("record_type") == "confirmed_medical_fact"
        and record.get("confirmation_status") == "confirmed"
        and record.get("payload", {}).get("field_code") == "diagnosis"
        and record.get("payload", {}).get("value", {}).get("certainty") == "explicit"
        for record in records
    )


class AdviceCallbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    schema_version: Literal["1.0"]
    advice: list[AdviceItem] = Field(max_length=20)


class FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_type: Literal["helpful", "not_helpful", "not_applicable"]
    expected_version: int = Field(strict=True, ge=0)


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskPriorityContext(_StrictResponse):
    alert_id: UUID
    severity: Literal["seek_care", "emergency"]
    status: Literal["unread", "read", "reevaluated"]
    triggered_at: datetime


class AdviceEvidenceTargetRead(_StrictResponse):
    type: str
    id: UUID


class AdvicePatientEvidenceRead(_StrictResponse):
    evidence_type: Literal["patient"]
    source_type: Literal[
        "confirmed_medical_fact",
        "diet_record",
        "stool_record",
        "symptom_record",
        "mood_record",
        "medication_plan",
        "medication_checkin",
        "risk_alert",
    ]
    source_id: UUID
    source_version: int = Field(ge=1)
    locator: str | None = Field(max_length=160)
    source_deleted: bool
    target: AdviceEvidenceTargetRead | None


class AdviceKnowledgeEvidenceRead(_StrictResponse):
    evidence_type: Literal["knowledge"]
    knowledge_ref: str = Field(min_length=1, max_length=160)
    knowledge_version: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=240)
    publisher: str = Field(min_length=1, max_length=160)
    citation_url: AnyHttpUrl | None


class AdviceFeedbackRead(_StrictResponse):
    advice_id: UUID
    feedback_type: Literal["helpful", "not_helpful", "not_applicable"]
    version: int = Field(ge=1)


class AdviceFeedbackHistoryRead(_StrictResponse):
    feedback_type: Literal["helpful", "not_helpful", "not_applicable"]
    version: int = Field(ge=1)
    created_at: datetime


class AdviceUncertaintyRead(_StrictResponse):
    level: Literal["low", "moderate", "high"]
    reasons: list[Annotated[str, Field(max_length=240)]] = Field(max_length=10)


class AdviceApplicabilityRead(_StrictResponse):
    scope: Literal["general", "condition_specific"]
    limitations: list[Annotated[str, Field(max_length=240)]] = Field(max_length=10)


class AdviceSafetyBoundaryRead(_StrictResponse):
    not_diagnosis: Literal[True]
    not_prescription: Literal[True]
    risk_alert_priority: Literal[True]


class AdviceRead(_StrictResponse):
    id: UUID
    task_id: UUID
    category: Literal[
        "diet", "lifestyle", "record_management", "medication_adherence", "care_consultation"
    ]
    priority: Literal["routine", "important"]
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=3000)
    uncertainty: AdviceUncertaintyRead
    applicability: AdviceApplicabilityRead
    safety_boundary: AdviceSafetyBoundaryRead
    version: str = Field(min_length=1, max_length=32)
    status: Literal["new", "read", "archived"]
    basis_updated: bool
    basis_updated_at: datetime | None
    basis_update_reason: Literal["source_updated", "source_deleted", "fact_replaced"] | None
    risk_priority_context: RiskPriorityContext | None
    evidence: list[AdvicePatientEvidenceRead | AdviceKnowledgeEvidenceRead]
    feedback: AdviceFeedbackRead | None
    feedback_history: list[AdviceFeedbackHistoryRead]
    created_at: datetime


class AdvicePageRead(_StrictResponse):
    items: list[AdviceRead]
    next_cursor: str | None


def _advice_problem(status: int, code: str, detail: str, instance: str) -> dict[str, Any]:
    return {
        "type": f"https://gutcare.invalid/problems/{code.lower()}",
        "title": "Request validation failed" if status == 422 else "Request failed",
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": code,
        "request_id": f"00000000-0000-4000-8000-{status:012d}",
    }


def _advice_problem_responses(
    path: str, statuses: tuple[int, ...]
) -> dict[int | str, dict[str, Any]]:
    issues = {
        400: ("INVALID_CURSOR", "Advice cursor is invalid"),
        401: ("AUTHENTICATION_REQUIRED", "Authentication required"),
        404: ("RESOURCE_NOT_FOUND", "Resource not found"),
        409: ("RECORD_VERSION_CONFLICT", "Advice feedback version conflict"),
        422: ("VALIDATION_ERROR", "Request validation failed"),
        500: ("INTERNAL_ERROR", "Service temporarily unavailable"),
        503: ("SERVICE_UNAVAILABLE", "Advice service unavailable"),
    }
    return {
        status: problem_response(
            issues[status][1],
            _advice_problem(status, *issues[status], path),
        )
        for status in statuses
    }


def _advice_success_response(
    status: int, schema: str, description: str, *, advice_status: str = "new"
) -> dict[int | str, dict[str, Any]]:
    example: dict[str, Any]
    if schema == "AdvicePageRead":
        example = {"items": [_advice_example()], "next_cursor": None}
    elif schema == "AdviceFeedbackRead":
        example = {
            "advice_id": "019a0000-0000-7000-8000-000000000901",
            "feedback_type": "helpful",
            "version": 1,
        }
    else:
        example = _advice_example(status=advice_status)
    return {
        status: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{schema}"},
                    "examples": {"example": {"value": example}},
                }
            },
        }
    }


def _is_safe_knowledge_citation(value: str | AnyHttpUrl | None) -> bool:
    if value is None:
        return True
    try:
        parsed = urlsplit(str(value))
        return (
            parsed.scheme.lower() == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port != 0
        )
    except ValueError:
        return False


def _advice_example(*, status: str = "new") -> dict[str, Any]:
    return {
        "id": "019a0000-0000-7000-8000-000000000901",
        "task_id": "019a0000-0000-7000-8000-000000000801",
        "category": "record_management",
        "priority": "routine",
        "title": "继续记录相关情况",
        "body": "可继续记录相关情况供后续回顾",
        "uncertainty": {"level": "moderate", "reasons": ["记录数量有限"]},
        "applicability": {"scope": "general", "limitations": []},
        "safety_boundary": {
            "not_diagnosis": True,
            "not_prescription": True,
            "risk_alert_priority": True,
        },
        "version": "1.0",
        "status": status,
        "basis_updated": False,
        "basis_updated_at": None,
        "basis_update_reason": None,
        "risk_priority_context": None,
        "evidence": [],
        "feedback": None,
        "feedback_history": [],
        "created_at": "2026-10-01T00:00:00Z",
    }


class AdviceServiceLike(Protocol):
    def callback(self, task_id: UUID, payload: dict[str, Any]) -> None: ...
    def list(self, context: AuthContext, limit: int, cursor: str | None) -> dict[str, Any]: ...
    def get(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]: ...
    def mark_read(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]: ...
    def archive(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]: ...
    def feedback(
        self, context: AuthContext, advice_id: UUID, payload: dict[str, Any], key: str
    ) -> dict[str, Any]: ...


def _service(request: Request) -> AdviceServiceLike:
    svc = getattr(request.app.state, "advice_service", None)
    if svc is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Advice service unavailable")
    return cast(AdviceServiceLike, svc)


def _worker_service(request: Request) -> AdviceServiceLike:
    svc = getattr(request.app.state, "advice_worker_service", None)
    if svc is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Advice worker unavailable")
    return cast(AdviceServiceLike, svc)


def _agent(request: Request, authorization: str | None) -> None:
    token = request.app.state.settings.agent_service_token
    if (
        not token
        or not authorization
        or not authorization.startswith("Bearer ")
        or not hmac.compare_digest(authorization[7:], token)
    ):
        raise Problem(401, "AUTHENTICATION_REQUIRED", "Service authentication required")


@agent_router.post("/{task_id}/callback", status_code=204, operation_id="submitAdviceCallback")
def advice_callback(
    task_id: UUID,
    body: AdviceCallbackBody,
    request: Request,
    svc: Annotated[AdviceServiceLike, Depends(_worker_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _agent(request, authorization)
    svc.callback(task_id, body.model_dump(mode="json"))
    return Response(status_code=204)


@router.get(
    "",
    operation_id="listAdvice",
    response_model=AdvicePageRead,
    responses={
        **_advice_success_response(200, "AdvicePageRead", "患者建议稳定游标分页"),
        **_advice_problem_responses("/api/v1/advice", (400, 401, 404, 422, 500, 503)),
    },
)
def list_advice(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[AdviceServiceLike, Depends(_service)],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=128),
) -> dict[str, Any]:
    return svc.list(context, limit, cursor)


@router.get(
    "/{advice_id}",
    operation_id="getAdvice",
    response_model=AdviceRead,
    responses={
        **_advice_success_response(200, "AdviceRead", "建议详情与受控证据入口"),
        **_advice_problem_responses("/api/v1/advice/{advice_id}", (401, 404, 422, 500, 503)),
    },
)
def get_advice(
    advice_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[AdviceServiceLike, Depends(_service)],
) -> dict[str, Any]:
    return svc.get(context, advice_id)


@router.post(
    "/{advice_id}/read",
    operation_id="readAdvice",
    response_model=AdviceRead,
    responses={
        **_advice_success_response(
            200, "AdviceRead", "建议已读，依据变化状态独立保留", advice_status="read"
        ),
        **_advice_problem_responses("/api/v1/advice/{advice_id}/read", (401, 404, 422, 500, 503)),
    },
)
def read_advice(
    advice_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[AdviceServiceLike, Depends(_service)],
) -> dict[str, Any]:
    return svc.mark_read(context, advice_id)


@router.post(
    "/{advice_id}/archive",
    operation_id="archiveAdvice",
    response_model=AdviceRead,
    responses={
        **_advice_success_response(
            200, "AdviceRead", "建议已归档，依据变化状态独立保留", advice_status="archived"
        ),
        **_advice_problem_responses(
            "/api/v1/advice/{advice_id}/archive", (401, 404, 422, 500, 503)
        ),
    },
)
def archive_advice(
    advice_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[AdviceServiceLike, Depends(_service)],
) -> dict[str, Any]:
    return svc.archive(context, advice_id)


@router.put(
    "/{advice_id}/feedback",
    operation_id="updateAdviceFeedback",
    response_model=AdviceFeedbackRead,
    responses={
        **_advice_success_response(200, "AdviceFeedbackRead", "建议反馈的当前乐观版本"),
        **_advice_problem_responses(
            "/api/v1/advice/{advice_id}/feedback", (401, 404, 409, 422, 500, 503)
        ),
    },
)
def feedback(
    advice_id: UUID,
    body: FeedbackBody,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[AdviceServiceLike, Depends(_service)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return svc.feedback(context, advice_id, body.model_dump(mode="json"), key)


class AdviceService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _profile(db: Session, context: AuthContext) -> PatientProfile:
        db.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )
        profile = db.scalar(select(PatientProfile).where(PatientProfile.user_id == context.user_id))
        if profile is None or profile.deleted_at is not None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        account = db.get(UserAccount, context.user_id)
        if account is None or account.status != "active" or account.deleted_at is not None:
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        db.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(profile.id)},
        )
        return profile

    @staticmethod
    def _authorized(db: Session, patient_id: UUID) -> None:
        AdviceService._require_consents(
            db, patient_id, ("health_data_processing", "third_party_ai")
        )

    @staticmethod
    def _require_consents(db: Session, patient_id: UUID, kinds: tuple[str, ...]) -> None:
        for kind in kinds:
            consent = db.scalar(
                select(PatientConsent)
                .where(PatientConsent.patient_id == patient_id, PatientConsent.consent_type == kind)
                .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
                .limit(1)
            )
            if consent is None or not consent.granted:
                raise Problem(409, "CONSENT_REQUIRED", "Advice processing consent is required")

    @staticmethod
    def _source_state(db: Session, patient_id: UUID, ev: AdviceEvidence) -> tuple[bool, int | None]:
        models: dict[str, Any] = {
            "diet_record": DietRecord,
            "stool_record": StoolRecord,
            "symptom_record": SymptomRecord,
            "medication_plan": MedicationPlan,
            "medication_checkin": MedicationCheckin,
        }
        if ev.source_type in models:
            model = models[ev.source_type]
            source_row = db.execute(
                select(model).where(model.id == ev.source_id, model.patient_id == patient_id)
            ).scalar_one_or_none()
            if source_row is None or getattr(source_row, "deleted_at", None) is not None:
                return False, None
            if not AnalysisService._source_is_live(
                db,
                patient_id,
                {"source_type": ev.source_type, "source_id": str(ev.source_id)},
            ):
                return False, None
            return True, getattr(source_row, "record_version", ev.source_version)
        if ev.source_type == "mood_record":
            mood_row = db.scalar(
                select(MoodRecord).where(
                    MoodRecord.id == ev.source_id,
                    MoodRecord.patient_id == patient_id,
                    MoodRecord.deleted_at.is_(None),
                )
            )
            if mood_row is None:
                return False, None
            return AnalysisService._source_is_live(
                db,
                patient_id,
                {"source_type": "mood_record", "source_id": str(ev.source_id)},
            ), mood_row.record_version
        if ev.source_type == "confirmed_medical_fact":
            medical_row = db.execute(
                select(ConfirmedMedicalFact, MedicalFieldCandidate.record_version)
                .join(
                    MedicalFieldCandidate,
                    MedicalFieldCandidate.id == ConfirmedMedicalFact.candidate_id,
                )
                .where(
                    ConfirmedMedicalFact.id == ev.source_id,
                    ConfirmedMedicalFact.patient_id == patient_id,
                )
            ).first()
            if medical_row is None or medical_row[0].fact_status != "active":
                return False, None
            if not AnalysisService._source_is_live(
                db,
                patient_id,
                {"source_type": ev.source_type, "source_id": str(ev.source_id)},
            ):
                return False, None
            return True, medical_row[1]
        if ev.source_type == "risk_alert":
            alert_row = db.scalar(
                select(RiskAlert).where(
                    RiskAlert.id == ev.source_id, RiskAlert.patient_id == patient_id
                )
            )
            if alert_row is None:
                return False, None
            return AnalysisService._source_is_live(
                db, patient_id, {"source_type": "risk_alert", "source_id": str(ev.source_id)}
            ), alert_row.source_record_version
        return False, None

    @staticmethod
    def _risk_priority_context(db: Session, patient_id: UUID) -> dict[str, Any] | None:
        alert = db.scalar(
            select(RiskAlert)
            .where(
                RiskAlert.patient_id == patient_id,
                RiskAlert.severity.in_(("seek_care", "emergency")),
            )
            .order_by(desc(RiskAlert.triggered_at), desc(RiskAlert.id))
            .limit(1)
        )
        if alert is None:
            return None
        return {
            "alert_id": str(alert.id),
            "severity": alert.severity,
            "status": alert.status,
            "triggered_at": alert.triggered_at.isoformat(),
        }

    @staticmethod
    def _dto(
        db: Session, row: HealthAdvice, risk_priority_context: dict[str, Any] | None
    ) -> dict[str, Any]:
        evidence_rows = db.scalars(
            select(AdviceEvidence).where(
                AdviceEvidence.advice_id == row.id, AdviceEvidence.patient_id == row.patient_id
            )
        )
        evidence: list[dict[str, Any]] = []
        for ev in evidence_rows:
            if ev.evidence_type == "knowledge":
                evidence.append(
                    {
                        "evidence_type": "knowledge",
                        "knowledge_ref": ev.knowledge_ref,
                        "knowledge_version": ev.knowledge_version,
                        "title": ev.knowledge_title,
                        "publisher": ev.knowledge_publisher,
                        "citation_url": ev.citation_url,
                    }
                )
            else:
                live, current_version = AdviceService._source_state(db, row.patient_id, ev)
                changed = not live or current_version != ev.source_version
                evidence.append(
                    {
                        "evidence_type": "patient",
                        "source_type": ev.source_type,
                        "source_id": str(ev.source_id),
                        "source_version": ev.source_version,
                        "locator": ev.locator if live else None,
                        "source_deleted": not live or ev.source_deleted,
                        "target": {"type": ev.source_type, "id": str(ev.source_id)}
                        if live
                        else None,
                    }
                )
                if not live and ev.locator is not None:
                    ev.locator = None
                    ev.source_deleted = True
                if changed and not row.basis_updated:
                    row.basis_updated = True
                    row.basis_updated_at = datetime.now(UTC)
                    row.basis_update_reason = "source_deleted" if not live else "source_updated"
        feedback = db.get(AdviceFeedback, (row.id, row.patient_id))
        history = db.scalars(
            select(AdviceFeedbackEvent)
            .where(
                AdviceFeedbackEvent.advice_id == row.id,
                AdviceFeedbackEvent.patient_id == row.patient_id,
            )
            .order_by(AdviceFeedbackEvent.version)
        )
        return {
            "id": str(row.id),
            "task_id": str(row.task_id),
            "category": row.category,
            "priority": row.priority,
            "title": row.title,
            "body": row.body,
            "uncertainty": row.uncertainty,
            "applicability": row.applicability,
            "safety_boundary": row.safety_boundary,
            "version": row.version,
            "status": row.status,
            "basis_updated": row.basis_updated,
            "basis_updated_at": row.basis_updated_at.isoformat() if row.basis_updated_at else None,
            "basis_update_reason": row.basis_update_reason,
            "risk_priority_context": risk_priority_context,
            "created_at": row.created_at.isoformat(),
            "evidence": evidence,
            "feedback": {"feedback_type": feedback.feedback_type, "version": feedback.version}
            if feedback
            else None,
            "feedback_history": [
                {
                    "feedback_type": e.feedback_type,
                    "version": e.version,
                    "created_at": e.created_at.isoformat(),
                }
                for e in history
            ],
        }

    def callback(self, task_id: UUID, payload: dict[str, Any]) -> None:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._sessions.begin() as db:
            task = db.scalar(select(AnalysisTask).where(AnalysisTask.id == task_id))
            if task is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is not eligible for advice")
            patient_id = task.patient_id
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                    "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                ),
                {"patient_id": str(patient_id)},
            )
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(patient_id)},
            )
            task = db.scalar(
                select(AnalysisTask).where(AnalysisTask.id == task_id).with_for_update()
            )
            if task is None or task.patient_id != patient_id:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is not eligible for advice")
            self._authorized(db, patient_id)
            previous = db.scalar(
                select(AdviceCallback).where(
                    AdviceCallback.task_id == task_id,
                    AdviceCallback.callback_id == UUID(payload["callback_id"]),
                )
            )
            if previous:
                if previous.request_hash == digest:
                    return
                raise Problem(
                    409, "CALLBACK_ID_CONFLICT", "Callback id was used with different content"
                )
            if task.status not in {"succeeded", "partial"} or task.result_payload is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is not eligible for advice")
            snapshot = db.get(TaskInputSnapshot, task_id)
            if snapshot is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task snapshot is unavailable")
            records = snapshot.snapshot_payload.get("records", [])
            has_mood_snapshot = any(
                record.get("record_type") == "mood_record" for record in records
            )
            if has_mood_snapshot:
                self._require_consents(
                    db,
                    patient_id,
                    (
                        "health_data_processing",
                        "mood_data_processing",
                        "mood_ai_sharing",
                        "third_party_ai",
                    ),
                )
            has_explicit_diagnosis = _snapshot_has_explicit_diagnosis(records)
            if not has_explicit_diagnosis and any(
                advice.get("applicability", {}).get("scope") == "condition_specific"
                for advice in payload["advice"]
            ):
                raise Problem(
                    409,
                    "ADVICE_NOT_APPLICABLE",
                    "Condition-specific advice requires an explicitly confirmed diagnosis",
                )
            allowed = {
                (r["record_type"], r["record_id"], r["record_version"], r["locator"])
                for r in snapshot.snapshot_payload["records"]
            }
            for advice in payload["advice"]:
                # Structural safety declaration and cited source are mandatory.
                # Advice is not inferred from the F08 result.
                boundary = advice["safety_boundary"]
                if set(boundary) != {
                    "not_diagnosis",
                    "not_prescription",
                    "risk_alert_priority",
                } or boundary != {
                    "not_diagnosis": True,
                    "not_prescription": True,
                    "risk_alert_priority": True,
                }:
                    raise Problem(422, "INVALID_ADVICE", "Advice safety boundary is invalid")
                row = HealthAdvice(
                    patient_id=patient_id,
                    task_id=task_id,
                    category=advice["category"],
                    priority=advice["priority"],
                    title=advice["title"],
                    body=advice["body"],
                    uncertainty=advice["uncertainty"],
                    applicability=advice["applicability"],
                    safety_boundary=boundary,
                    version=advice["version"],
                )
                db.add(row)
                db.flush()
                for item in advice["evidence"]:
                    if item["evidence_type"] == "patient":
                        ref = (
                            item["source_type"],
                            str(item["source_id"]),
                            item["source_version"],
                            item["locator"],
                        )
                        if ref not in allowed:
                            raise Problem(
                                422,
                                "INVALID_EVIDENCE",
                                "Evidence must exactly match this task snapshot",
                            )
                        db.add(
                            AdviceEvidence(
                                advice_id=row.id,
                                patient_id=patient_id,
                                evidence_type="patient",
                                source_type=item["source_type"],
                                source_id=UUID(item["source_id"]),
                                source_version=item["source_version"],
                                locator=item["locator"],
                            )
                        )
                    else:
                        url = item.get("citation_url")
                        if not _is_safe_knowledge_citation(url):
                            raise Problem(
                                422,
                                "INVALID_EVIDENCE",
                                "Knowledge citation must be an HTTPS URL without user information",
                            )
                        db.add(
                            AdviceEvidence(
                                advice_id=row.id,
                                patient_id=patient_id,
                                evidence_type="knowledge",
                                knowledge_ref=item["knowledge_ref"],
                                knowledge_version=item["knowledge_version"],
                                knowledge_title=item["knowledge_title"],
                                knowledge_publisher=item["knowledge_publisher"],
                                citation_url=url,
                            )
                        )
            db.add(
                AdviceCallback(
                    task_id=task_id,
                    patient_id=patient_id,
                    callback_id=UUID(payload["callback_id"]),
                    request_hash=digest,
                )
            )

    @staticmethod
    def _encode_cursor(created_at: datetime, advice_id: UUID) -> str:
        payload = f"{created_at.astimezone(UTC).isoformat()}|{advice_id}"
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cursor):
                raise ValueError
            decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            created_at_text, advice_id_text = decoded.split("|", 1)
            created_at = datetime.fromisoformat(created_at_text)
            advice_id = UUID(advice_id_text)
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError
            if AdviceService._encode_cursor(created_at, advice_id) != cursor:
                raise ValueError
            return created_at.astimezone(UTC), advice_id
        except (ValueError, UnicodeDecodeError, TypeError):
            raise Problem(400, "INVALID_CURSOR", "Advice cursor is invalid") from None

    def list(self, context: AuthContext, limit: int, cursor: str | None = None) -> dict[str, Any]:
        with self._sessions.begin() as db:
            p = self._profile(db, context)
            statement = select(HealthAdvice).where(HealthAdvice.patient_id == p.id)
            if cursor is not None:
                created_at, advice_id = self._decode_cursor(cursor)
                statement = statement.where(
                    tuple_(HealthAdvice.created_at, HealthAdvice.id) < (created_at, advice_id)
                )
            rows = list(
                db.scalars(
                    statement.order_by(desc(HealthAdvice.created_at), desc(HealthAdvice.id)).limit(
                        limit + 1
                    )
                )
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            risk_priority_context = self._risk_priority_context(db, p.id)
            next_cursor = (
                self._encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
            )
            return {
                "items": [self._dto(db, row, risk_priority_context) for row in rows],
                "next_cursor": next_cursor,
            }

    def get(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            p = self._profile(db, context)
            row = db.scalar(
                select(HealthAdvice).where(
                    HealthAdvice.id == advice_id, HealthAdvice.patient_id == p.id
                )
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(db, row, self._risk_priority_context(db, p.id))

    def _change(self, context: AuthContext, advice_id: UUID, status: str) -> dict[str, Any]:
        with self._sessions.begin() as db:
            p = self._profile(db, context)
            row = db.scalar(
                select(HealthAdvice)
                .where(HealthAdvice.id == advice_id, HealthAdvice.patient_id == p.id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            now = datetime.now(UTC)
            if status == "read" and row.status == "new":
                row.status, row.read_at = "read", now
            elif status == "archived":
                row.status, row.archived_at = "archived", now
            return self._dto(db, row, self._risk_priority_context(db, p.id))

    def mark_read(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]:
        return self._change(context, advice_id, "read")

    def archive(self, context: AuthContext, advice_id: UUID) -> dict[str, Any]:
        return self._change(context, advice_id, "archived")

    def feedback(
        self, context: AuthContext, advice_id: UUID, payload: dict[str, Any], key: str
    ) -> dict[str, Any]:
        with self._sessions.begin() as db:
            p = self._profile(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "'gutcare.advice-feedback:' || :patient_id || ':' || :key, 0))"
                ),
                {"patient_id": str(p.id), "key": key},
            )
            row = db.scalar(
                select(HealthAdvice)
                .where(HealthAdvice.id == advice_id, HealthAdvice.patient_id == p.id)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            event = db.scalar(
                select(AdviceFeedbackEvent).where(
                    AdviceFeedbackEvent.patient_id == p.id,
                    AdviceFeedbackEvent.idempotency_key == key,
                )
            )
            if event:
                if event.request_hash == digest and event.advice_id == advice_id:
                    current = db.get(AdviceFeedback, (advice_id, p.id))
                    if current is None:
                        raise Problem(
                            409, "RECORD_VERSION_CONFLICT", "Feedback history is unavailable"
                        )
                    return {
                        "advice_id": str(advice_id),
                        "feedback_type": current.feedback_type,
                        "version": current.version,
                    }
                raise Problem(
                    409, "IDEMPOTENCY_CONFLICT", "Idempotency key was used with different content"
                )
            current = db.get(AdviceFeedback, (advice_id, p.id))
            version = current.version if current else 0
            if payload["expected_version"] != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Feedback version is stale")
            new_version = version + 1
            if current:
                current.feedback_type, current.version, current.updated_at = (
                    payload["feedback_type"],
                    new_version,
                    datetime.now(UTC),
                )
            else:
                current = AdviceFeedback(
                    advice_id=advice_id,
                    patient_id=p.id,
                    feedback_type=payload["feedback_type"],
                    version=new_version,
                )
                db.add(current)
            db.add(
                AdviceFeedbackEvent(
                    advice_id=advice_id,
                    patient_id=p.id,
                    idempotency_key=key,
                    request_hash=digest,
                    feedback_type=payload["feedback_type"],
                    version=new_version,
                )
            )
            return {
                "advice_id": str(advice_id),
                "feedback_type": current.feedback_type,
                "version": current.version,
            }
