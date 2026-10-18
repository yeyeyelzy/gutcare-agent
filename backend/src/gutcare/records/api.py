"""HTTP API for diet, stool, symptom records and risk alerts."""

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")
risk_router = APIRouter(prefix="/api/v1")
RecordType = Literal["diet-records", "stool-records", "symptom-records"]
AUTH_PROBLEM_RESPONSE: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "RFC 9457 Problem Details: missing or invalid authentication",
        "content": {"application/problem+json": {"schema": {"type": "object"}}},
    }
}
SymptomCode = Literal[
    "abdominal_pain",
    "bloating",
    "diarrhea",
    "constipation",
    "nausea",
    "vomiting",
    "acid_reflux",
    "appetite_change",
    "blood_in_stool_concern",
    "other",
]


class RecordServicePort(Protocol):
    def create(
        self,
        context: AuthContext,
        record_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]: ...
    def list(
        self,
        context: AuthContext,
        record_type: str,
        *,
        limit: int,
        cursor: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]: ...
    def get(self, context: AuthContext, record_type: str, record_id: UUID) -> dict[str, Any]: ...
    def patch(
        self,
        context: AuthContext,
        record_type: str,
        record_id: UUID,
        version: int,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...
    def delete(
        self, context: AuthContext, record_type: str, record_id: UUID, version: int
    ) -> None: ...
    def symptom_status_history(self, context: AuthContext, record_id: UUID) -> dict[str, Any]: ...
    def alerts(
        self, context: AuthContext, *, limit: int, cursor: str | None, unread_only: bool = False
    ) -> dict[str, Any]: ...
    def get_alert(
        self, context: AuthContext, alert_id: UUID, mark_read: bool = False
    ) -> dict[str, Any]: ...
    def reevaluate_alert(self, context: AuthContext, alert_id: UUID) -> dict[str, Any]: ...


class DietItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    category_code: str | None = Field(default=None, max_length=64)
    amount_text: str | None = Field(default=None, max_length=160)


class DietPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meal_type: str | None = Field(default=None, pattern="^(breakfast|lunch|dinner|snack|other)$")
    text_description: str | None = Field(default=None, max_length=4000)
    items: list[DietItemInput] = Field(default_factory=list, max_length=50)
    portion_note: str | None = Field(default=None, max_length=160)
    cooking_method: str | None = Field(default=None, max_length=160)
    subjective_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_content(self) -> "DietPayload":
        if not (self.text_description and self.text_description.strip()) and not self.items:
            raise ValueError("diet record needs a description or at least one food item")
        return self


class StoolPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bristol_type: int | None = Field(default=None, ge=1, le=7)
    color_code: str | None = Field(default=None, max_length=32)
    blood_reported: bool | None = None
    urgency_level: int | None = Field(default=None, ge=0, le=10)
    bowel_amount: str | None = Field(default=None, max_length=32)
    process_sensation: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class SymptomItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symptom_code: SymptomCode
    other_description: str | None = Field(default=None, min_length=1, max_length=160)
    severity: int | None = Field(default=None, ge=0, le=10)
    body_location: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_other_description(self) -> "SymptomItemInput":
        if (self.symptom_code == "other") != (self.other_description is not None):
            raise ValueError("other_description is required only when symptom_code is other")
        return self


class SymptomPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SymptomItemInput] = Field(min_length=1, max_length=30)
    duration_minutes: int | None = Field(default=None, ge=0, le=10080)
    notes: str | None = Field(default=None, max_length=2000)
    companion_signs: list[str] = Field(default_factory=list, max_length=30)
    symptom_status: Literal["ongoing", "relieved"] = "ongoing"


class RecordWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: datetime
    payload: DietPayload | StoolPayload | SymptomPayload
    record_version: int | None = Field(default=None, ge=1)


class SymptomStatusEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ongoing", "relieved"]
    record_version: int = Field(ge=1)
    changed_at: datetime


class SymptomStatusHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", title="SymptomStatusHistory")
    symptom_record_id: UUID
    current_status: Literal["ongoing", "relieved"]
    events: list[SymptomStatusEventRead]


def validate_payload(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, type[BaseModel]] = {
        "diet-records": DietPayload,
        "stool-records": StoolPayload,
        "symptom-records": SymptomPayload,
    }
    schema = schemas.get(record_type)
    if schema is None:
        raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
    try:
        return schema.model_validate(payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            "Invalid record payload",
            errors=[
                {"location": list(e["loc"]), "code": e["type"], "message": e["msg"]}
                for e in exc.errors()
            ],
        ) from exc


def get_record_service(request: Request) -> RecordServicePort:
    service: RecordServicePort | None = request.app.state.record_service
    if service is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return service


@router.get(
    "/{record_type}", operation_id="listRecords", tags=["Records"], responses=AUTH_PROBLEM_RESPONSE
)
def list_records(
    record_type: RecordType,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    if since and since.tzinfo is None or until and until.tzinfo is None:
        raise Problem(422, "VALIDATION_ERROR", "Time filters must include a timezone")
    if since and until and since >= until:
        raise Problem(422, "VALIDATION_ERROR", "since must be earlier than until")
    return service.list(context, record_type, limit=limit, cursor=cursor, since=since, until=until)


@router.post(
    "/{record_type}",
    operation_id="createRecord",
    tags=["Records"],
    status_code=status.HTTP_201_CREATED,
    responses=AUTH_PROBLEM_RESPONSE,
)
def create_record(
    record_type: RecordType,
    body: RecordWrite,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    if body.record_version is not None:
        raise Problem(422, "VALIDATION_ERROR", "record_version is only accepted for updates")
    return service.create(
        context,
        record_type,
        body.occurred_at,
        validate_payload(record_type, body.payload.model_dump(exclude_unset=True)),
        idempotency_key,
    )


@router.get(
    "/{record_type}/{record_id}",
    operation_id="getRecord",
    tags=["Records"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def get_record(
    record_type: RecordType,
    record_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    return service.get(context, record_type, record_id)


@router.patch(
    "/{record_type}/{record_id}",
    operation_id="updateRecord",
    tags=["Records"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def patch_record(
    record_type: RecordType,
    record_id: UUID,
    body: RecordWrite,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    if body.record_version is None:
        raise Problem(422, "VALIDATION_ERROR", "record_version is required")
    return service.patch(
        context,
        record_type,
        record_id,
        body.record_version,
        body.occurred_at,
        validate_payload(record_type, body.payload.model_dump(exclude_unset=True)),
    )


@router.delete(
    "/{record_type}/{record_id}",
    operation_id="deleteRecord",
    tags=["Records"],
    status_code=status.HTTP_204_NO_CONTENT,
    responses=AUTH_PROBLEM_RESPONSE,
)
def delete_record(
    record_type: RecordType,
    record_id: UUID,
    record_version: Annotated[int, Query(ge=1)],
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> Response:
    service.delete(context, record_type, record_id, record_version)
    return Response(status_code=204)


@router.get(
    "/symptom-records/{record_id}/status-history",
    operation_id="getSymptomStatusHistory",
    tags=["Records"],
    response_model=SymptomStatusHistory,
    responses=AUTH_PROBLEM_RESPONSE,
)
def symptom_status_history(
    record_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    return service.symptom_status_history(context, record_id)


@risk_router.get(
    "/risk-alerts",
    operation_id="listRiskAlerts",
    tags=["Risk Alerts"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def list_alerts(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    unread_only: bool = False,
) -> dict[str, Any]:
    return service.alerts(context, limit=limit, cursor=cursor, unread_only=unread_only)


@risk_router.get(
    "/risk-alerts/{alert_id}",
    operation_id="getRiskAlert",
    tags=["Risk Alerts"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def get_alert(
    alert_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    return service.get_alert(context, alert_id)


@risk_router.post(
    "/risk-alerts/{alert_id}/read",
    operation_id="markRiskAlertRead",
    tags=["Risk Alerts"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def mark_alert_read(
    alert_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    return service.get_alert(context, alert_id, mark_read=True)


@risk_router.post(
    "/risk-alerts/{alert_id}/reevaluate",
    operation_id="reevaluateRiskAlert",
    tags=["Risk Alerts"],
    responses=AUTH_PROBLEM_RESPONSE,
)
def reevaluate_alert(
    alert_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[RecordServicePort, Depends(get_record_service)],
) -> dict[str, Any]:
    return service.reevaluate_alert(context, alert_id)
