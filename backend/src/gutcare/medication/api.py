"""Strict F06 HTTP DTOs and routes."""

from datetime import date, datetime, time
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "RFC 9457 Problem Details",
        "content": {"application/problem+json": {"schema": {"type": "object"}}},
    }
    for code in (401, 404, 409, 422)
}
router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSES)


class MedicationPort(Protocol):
    def create_plan(
        self, context: AuthContext, payload: dict[str, Any], key: str
    ) -> dict[str, Any]: ...
    def list_plans(self, context: AuthContext) -> list[dict[str, Any]]: ...
    def get_plan(self, context: AuthContext, plan_id: UUID) -> dict[str, Any]: ...
    def list_schedules(self, context: AuthContext, plan_id: UUID) -> list[dict[str, Any]]: ...
    def patch_plan(
        self, context: AuthContext, plan_id: UUID, version: int, payload: dict[str, Any]
    ) -> dict[str, Any]: ...
    def transition_plan(
        self, context: AuthContext, plan_id: UUID, version: int, action: str, key: str
    ) -> dict[str, Any]: ...
    def delete_plan(self, context: AuthContext, plan_id: UUID, version: int) -> None: ...
    def save_schedule(
        self,
        context: AuthContext,
        plan_id: UUID | None,
        schedule_id: UUID | None,
        version: int | None,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]: ...
    def delete_schedule(self, context: AuthContext, schedule_id: UUID, version: int) -> None: ...
    def list_checkins(
        self, context: AuthContext, start: date, end: date
    ) -> list[dict[str, Any]]: ...
    def list_today_checkins(self, context: AuthContext) -> list[dict[str, Any]]: ...
    def update_checkin(
        self, context: AuthContext, checkin_id: UUID, version: int, payload: dict[str, Any]
    ) -> dict[str, Any]: ...


def service(request: Request) -> MedicationPort:
    target: MedicationPort | None = request.app.state.medication_service
    if target is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return target


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanCreate(Strict):
    medication_name: str = Field(min_length=1, max_length=160)
    dosage_text: str | None = Field(default=None, max_length=160)
    route_code: str | None = Field(default=None, max_length=32)
    start_date: date | None = None
    end_date: date | None = None
    source_type: Literal["manual", "medical_document"]
    source_document_id: UUID | None = None

    @model_validator(mode="after")
    def source_matches(self) -> "PlanCreate":
        if (self.source_type == "manual") != (self.source_document_id is None):
            raise ValueError("source_document_id must match source_type")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class PlanPatch(Strict):
    record_version: int = Field(ge=1)
    medication_name: str | None = Field(default=None, min_length=1, max_length=160)
    dosage_text: str | None = Field(default=None, max_length=160)
    route_code: str | None = Field(default=None, max_length=32)
    start_date: date | None = None
    end_date: date | None = None
    confirmation_status: Literal["confirmed", "needs_review"] | None = None

    @field_validator("medication_name", "confirmation_status", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class VersionRequest(Strict):
    record_version: int = Field(ge=1)


class TransitionRequest(VersionRequest):
    action: Literal["confirm", "review", "activate", "end", "discontinue"]


class ScheduleWrite(Strict):
    local_time: time
    timezone: str = Field(min_length=1, max_length=64)
    rrule: str | None = Field(default=None, max_length=256)
    valid_from: date
    valid_to: date | None = None
    enabled: bool = True
    record_version: int | None = Field(default=None, ge=1)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def dates_match(self) -> "ScheduleWrite":
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        return self


class CheckinUpdate(Strict):
    record_version: int = Field(ge=1)
    status: Literal["taken", "not_taken", "pending", "skipped"]
    taken_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def taken_timestamp(self) -> "CheckinUpdate":
        if self.status == "taken" and self.taken_at is None:
            raise ValueError("taken_at required for taken status")
        if self.status != "taken" and self.taken_at is not None:
            raise ValueError("taken_at only allowed for taken status")
        if self.taken_at and self.taken_at.tzinfo is None:
            raise ValueError("taken_at requires timezone")
        return self


def context(credentials: Annotated[AuthContext, Depends(current_auth_context)]) -> AuthContext:
    return credentials


@router.post(
    "/medication-plans", status_code=201, operation_id="createMedicationPlan", tags=["Medication"]
)
def create_plan(
    body: PlanCreate,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return target.create_plan(ctx, body.model_dump(), idempotency_key)


@router.get("/medication-plans", operation_id="listMedicationPlans", tags=["Medication"])
def list_plans(
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> list[dict[str, Any]]:
    return target.list_plans(ctx)


@router.get(
    "/medication-plans/{plan_id}",
    operation_id="getMedicationPlan",
    tags=["Medication"],
)
def get_plan(
    plan_id: UUID,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> dict[str, Any]:
    return target.get_plan(ctx, plan_id)


@router.patch(
    "/medication-plans/{plan_id}", operation_id="updateMedicationPlan", tags=["Medication"]
)
def patch_plan(
    plan_id: UUID,
    body: PlanPatch,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> dict[str, Any]:
    return target.patch_plan(
        ctx,
        plan_id,
        body.record_version,
        body.model_dump(exclude={"record_version"}, exclude_unset=True),
    )


@router.post(
    "/medication-plans/{plan_id}/transitions",
    operation_id="transitionMedicationPlan",
    tags=["Medication"],
)
def transition(
    plan_id: UUID,
    body: TransitionRequest,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    return target.transition_plan(ctx, plan_id, body.record_version, body.action, idempotency_key)


@router.delete(
    "/medication-plans/{plan_id}",
    status_code=204,
    operation_id="deleteMedicationPlan",
    tags=["Medication"],
)
def delete_plan(
    plan_id: UUID,
    record_version: Annotated[int, Query(ge=1)],
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> Response:
    target.delete_plan(ctx, plan_id, record_version)
    return Response(status_code=204)


@router.post(
    "/medication-plans/{plan_id}/schedules",
    status_code=201,
    operation_id="createMedicationSchedule",
    tags=["Medication"],
)
def create_schedule(
    plan_id: UUID,
    body: ScheduleWrite,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    if body.record_version is not None:
        raise Problem(422, "VALIDATION_ERROR", "record_version must be omitted on create")
    return target.save_schedule(
        ctx,
        plan_id,
        None,
        None,
        body.model_dump(exclude={"record_version"}),
        idempotency_key,
    )


@router.get(
    "/medication-plans/{plan_id}/schedules",
    operation_id="listMedicationSchedules",
    tags=["Medication"],
)
def list_schedules(
    plan_id: UUID,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> list[dict[str, Any]]:
    return target.list_schedules(ctx, plan_id)


@router.patch(
    "/medication-schedules/{schedule_id}",
    operation_id="updateMedicationSchedule",
    tags=["Medication"],
)
def patch_schedule(
    schedule_id: UUID,
    body: ScheduleWrite,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> dict[str, Any]:
    if body.record_version is None:
        raise Problem(422, "VALIDATION_ERROR", "record_version required")
    # The owning plan is resolved inside the service; clients cannot switch patient scope.
    return target.save_schedule(
        ctx, None, schedule_id, body.record_version, body.model_dump(exclude={"record_version"})
    )


@router.delete(
    "/medication-schedules/{schedule_id}",
    status_code=204,
    operation_id="deleteMedicationSchedule",
    tags=["Medication"],
)
def delete_schedule(
    schedule_id: UUID,
    record_version: Annotated[int, Query(ge=1)],
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> Response:
    target.delete_schedule(ctx, schedule_id, record_version)
    return Response(status_code=204)


@router.get("/medication-checkins", operation_id="listMedicationCheckins", tags=["Medication"])
def list_checkins(
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> list[dict[str, Any]]:
    return target.list_checkins(ctx, start, end)


@router.get(
    "/medication-checkins/today", operation_id="listTodayMedicationCheckins", tags=["Medication"]
)
def today_checkins(
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> list[dict[str, Any]]:
    return target.list_today_checkins(ctx)


@router.patch(
    "/medication-checkins/{checkin_id}", operation_id="updateMedicationCheckin", tags=["Medication"]
)
def update_checkin(
    checkin_id: UUID,
    body: CheckinUpdate,
    ctx: Annotated[AuthContext, Depends(context)],
    target: Annotated[MedicationPort, Depends(service)],
) -> dict[str, Any]:
    return target.update_checkin(
        ctx, checkin_id, body.record_version, body.model_dump(exclude={"record_version"})
    )
