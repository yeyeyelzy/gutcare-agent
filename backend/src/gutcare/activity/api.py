"""F07 activity and F11 history/trend HTTP contract."""

# FastAPI dependency injection uses callable defaults by design.
# ruff: noqa: B008

from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1", tags=["activity-history"])


class ActivityPort(Protocol):
    def create(self, context: AuthContext, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, context: AuthContext, ident: UUID) -> dict[str, Any]: ...
    def update(
        self, context: AuthContext, ident: UUID, version: int, changes: dict[str, Any]
    ) -> dict[str, Any]: ...
    def delete(self, context: AuthContext, ident: UUID, version: int) -> None: ...
    def list_activities(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]: ...
    def timeline(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        categories: list[str] | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]: ...
    def trends(
        self, context: AuthContext, start: datetime, end: datetime, bucket: str
    ) -> dict[str, Any]: ...


def service(request: Request) -> ActivityPort:
    target: ActivityPort | None = request.app.state.activity_service
    if target is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return target


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActivityWrite(Strict):
    activity_type: Literal["walking", "jogging", "cycling", "other"]
    description: str | None = Field(default=None, min_length=1, max_length=160)
    intensity: Literal["low", "moderate", "high"]
    subjective_feeling: Literal["better", "same", "worse"]
    duration_minutes: int = Field(ge=1, le=1440)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include timezone")
        return value

    @model_validator(mode="after")
    def other_description(self) -> "ActivityWrite":
        if (self.activity_type == "other") != (self.description is not None):
            raise ValueError("description is required only for activity_type=other")
        if self.description is not None:
            self.description = self.description.strip()
            if not self.description:
                raise ValueError("description cannot be blank")
        return self


class ActivityPatch(Strict):
    record_version: int = Field(ge=1)
    activity_type: Literal["walking", "jogging", "cycling", "other"] | None = None
    description: str | None = Field(default=None, min_length=1, max_length=160)
    intensity: Literal["low", "moderate", "high"] | None = None
    subjective_feeling: Literal["better", "same", "worse"] | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    occurred_at: datetime | None = None

    @field_validator(
        "activity_type",
        "intensity",
        "subjective_feeling",
        "duration_minutes",
        "occurred_at",
        mode="before",
    )
    @classmethod
    def required_patch_fields_cannot_be_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("occurred_at")
    @classmethod
    def patch_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("occurred_at must include timezone")
        return value

    @field_validator("description")
    @classmethod
    def normalize_patch_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("description cannot be blank")
        return value


class Version(Strict):
    record_version: int = Field(ge=1)


@router.post("/activity-records", status_code=201)
def create_activity(
    payload: ActivityWrite,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    return svc.create(context, payload.model_dump())


@router.get("/activity-records")
def list_activities(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=512),
    since: datetime | None = None,
    until: datetime | None = None,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    return svc.list_activities(context, limit, cursor, since, until)


@router.get("/activity-records/{record_id}")
def get_activity(
    record_id: UUID,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    return svc.get(context, record_id)


@router.patch("/activity-records/{record_id}")
def update_activity(
    record_id: UUID,
    payload: ActivityPatch,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    version = values.pop("record_version")
    return svc.update(context, record_id, version, values)


@router.delete("/activity-records/{record_id}", status_code=204)
def delete_activity(
    record_id: UUID,
    payload: Version,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> Response:
    svc.delete(context, record_id, payload.record_version)
    return Response(status_code=204)


@router.get("/history/timeline")
def timeline(
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=512),
    category: list[str] | None = Query(None),
    since: datetime | None = None,
    until: datetime | None = None,
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    return svc.timeline(context, limit, cursor, category, since, until)


@router.get("/trends")
def trends(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(alias="to"),
    bucket: Literal["day", "week"] = "day",
    context: AuthContext = Depends(current_auth_context),
    svc: ActivityPort = Depends(service),
) -> dict[str, Any]:
    if from_.tzinfo is None or to.tzinfo is None:
        raise Problem(422, "VALIDATION_ERROR", "Trend bounds must include timezone")
    return svc.trends(context, from_, to, bucket)
