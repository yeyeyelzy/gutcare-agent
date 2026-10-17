"""F07 activity and F11 history/trend HTTP contract."""

# FastAPI dependency injection uses callable defaults by design.
# ruff: noqa: B008

from datetime import date, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gutcare.auth.api import current_auth_context, problem_response
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


class TrendActivityItem(Strict):
    bucket: str
    count: int = Field(ge=0)
    duration_minutes: int = Field(ge=0)


class TrendStoolItem(Strict):
    bucket: str
    has_data: bool
    count: int = Field(ge=0)
    bristol_confirmed_count: int = Field(ge=0)
    bristol_unknown_count: int = Field(ge=0)


class TrendSymptomItem(Strict):
    bucket: str
    has_data: bool
    count: int = Field(ge=0)
    mean_severity: float | None = Field(ge=0, le=10)
    status: Literal["ongoing", "relieved"]


class TrendDietItem(Strict):
    bucket: str
    category: str
    count: int = Field(ge=0)


class TrendMedicationItem(Strict):
    bucket: str
    status: Literal["pending", "taken", "not_taken", "skipped"]
    count: int = Field(ge=0)


class TrendActivity(Strict):
    has_data: bool
    items: list[TrendActivityItem]


class TrendStool(Strict):
    has_data: bool
    items: list[TrendStoolItem]


class TrendSymptom(Strict):
    has_data: bool
    items: list[TrendSymptomItem]


class TrendDiet(Strict):
    has_data: bool
    items: list[TrendDietItem]


class TrendMedication(Strict):
    has_data: bool
    items: list[TrendMedicationItem]


class MoodLevelCounts(Strict):
    level_1: int = Field(alias="1", ge=0)
    level_2: int = Field(alias="2", ge=0)
    level_3: int = Field(alias="3", ge=0)
    level_4: int = Field(alias="4", ge=0)
    level_5: int = Field(alias="5", ge=0)


class MoodTrendBucketResponse(Strict):
    period_start: date
    period_end: date
    has_data: bool
    record_count: int = Field(ge=0)
    mood_level_counts: MoodLevelCounts


class MoodTrendAvailableResponse(Strict):
    availability: Literal["available"]
    buckets: list[MoodTrendBucketResponse]


class MoodTrendUnavailableResponse(Strict):
    availability: Literal["consent_required"]
    reason_code: Literal["CONSENT_REQUIRED"]
    missing_consents: list[Literal["health_data_processing", "mood_data_processing"]] = Field(
        min_length=1, max_length=2
    )


TrendMood = Annotated[
    MoodTrendAvailableResponse | MoodTrendUnavailableResponse,
    Field(discriminator="availability"),
]


class TrendResponse(Strict):
    timezone: str
    from_: datetime = Field(alias="from")
    to: datetime
    bucket: Literal["day", "week"]
    activity: TrendActivity
    stool: TrendStool
    symptom: TrendSymptom
    diet_confirmed_categories: TrendDiet
    medication_checkins: TrendMedication
    mood: TrendMood


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


@router.get(
    "/history/timeline",
    operation_id="getHistoryTimeline",
    responses={
        401: problem_response(
            "需要有效患者会话",
            {
                "type": "https://gutcare.invalid/problems/authentication_required",
                "title": "Authentication required",
                "status": 401,
                "detail": "Authentication required",
                "instance": "/api/v1/history/timeline",
                "code": "AUTHENTICATION_REQUIRED",
                "request_id": "00000000-0000-4000-8000-000000000003",
            },
        ),
        400: problem_response(
            "时间线游标无效或与当前筛选不匹配",
            {
                "type": "https://gutcare.invalid/problems/invalid_cursor",
                "title": "时间线游标无效",
                "status": 400,
                "detail": "History cursor is invalid",
                "instance": "/api/v1/history/timeline",
                "code": "INVALID_CURSOR",
                "request_id": "00000000-0000-4000-8000-000000000001",
            },
        ),
        422: problem_response(
            "时间范围、类别或分页参数无效",
            {
                "type": "https://gutcare.invalid/problems/validation_error",
                "title": "Request validation failed",
                "status": 422,
                "detail": "History time range must be timezone-aware and non-empty",
                "instance": "/api/v1/history/timeline",
                "code": "VALIDATION_ERROR",
                "request_id": "00000000-0000-4000-8000-000000000002",
                "errors": [],
            },
        ),
    },
)
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


@router.get(
    "/trends",
    operation_id="getTrends",
    response_model=TrendResponse,
    responses={
        200: {
            "description": "请求范围内的本人趋势聚合；mood 可用或因授权不可用",
            "content": {
                "application/json": {
                    "examples": {
                        "available": {
                            "value": {
                                "timezone": "Asia/Shanghai",
                                "from": "2026-10-01T00:00:00+08:00",
                                "to": "2026-10-08T00:00:00+08:00",
                                "bucket": "day",
                                "activity": {
                                    "has_data": True,
                                    "items": [
                                        {
                                            "bucket": "2026-10-01T00:00:00",
                                            "count": 1,
                                            "duration_minutes": 30,
                                        }
                                    ],
                                },
                                "stool": {
                                    "has_data": True,
                                    "items": [
                                        {
                                            "bucket": "2026-10-01T00:00:00",
                                            "has_data": True,
                                            "count": 2,
                                            "bristol_confirmed_count": 1,
                                            "bristol_unknown_count": 1,
                                        }
                                    ],
                                },
                                "symptom": {
                                    "has_data": True,
                                    "items": [
                                        {
                                            "bucket": "2026-10-01T00:00:00",
                                            "has_data": True,
                                            "count": 1,
                                            "mean_severity": 2.5,
                                            "status": "ongoing",
                                        }
                                    ],
                                },
                                "diet_confirmed_categories": {
                                    "has_data": True,
                                    "items": [
                                        {
                                            "bucket": "2026-10-01T00:00:00",
                                            "category": "vegetable",
                                            "count": 1,
                                        }
                                    ],
                                },
                                "medication_checkins": {
                                    "has_data": True,
                                    "items": [
                                        {
                                            "bucket": "2026-10-01T00:00:00",
                                            "status": "taken",
                                            "count": 1,
                                        }
                                    ],
                                },
                                "mood": {
                                    "availability": "available",
                                    "buckets": [
                                        {
                                            "period_start": "2026-10-01",
                                            "period_end": "2026-10-02",
                                            "has_data": True,
                                            "record_count": 1,
                                            "mood_level_counts": {
                                                "1": 0,
                                                "2": 0,
                                                "3": 1,
                                                "4": 0,
                                                "5": 0,
                                            },
                                        }
                                    ],
                                },
                            }
                        },
                        "mood_consent_required": {
                            "value": {
                                "timezone": "Asia/Shanghai",
                                "from": "2026-10-01T00:00:00+08:00",
                                "to": "2026-10-08T00:00:00+08:00",
                                "bucket": "day",
                                "activity": {"has_data": False, "items": []},
                                "stool": {"has_data": False, "items": []},
                                "symptom": {"has_data": False, "items": []},
                                "diet_confirmed_categories": {"has_data": False, "items": []},
                                "medication_checkins": {"has_data": False, "items": []},
                                "mood": {
                                    "availability": "consent_required",
                                    "reason_code": "CONSENT_REQUIRED",
                                    "missing_consents": ["mood_data_processing"],
                                },
                            }
                        },
                    }
                }
            },
        },
        401: problem_response(
            "需要有效患者会话",
            {
                "type": "https://gutcare.invalid/problems/authentication_required",
                "title": "Authentication required",
                "status": 401,
                "detail": "Authentication required",
                "instance": "/api/v1/trends",
                "code": "AUTHENTICATION_REQUIRED",
                "request_id": "00000000-0000-4000-8000-000000000003",
            },
        ),
        422: problem_response(
            "趋势时间范围或 bucket 参数无效",
            {
                "type": "https://gutcare.invalid/problems/validation_error",
                "title": "Request validation failed",
                "status": 422,
                "detail": "Trend bounds must include timezone and define a non-empty range",
                "instance": "/api/v1/trends",
                "code": "VALIDATION_ERROR",
                "request_id": "00000000-0000-4000-8000-000000000002",
                "errors": [],
            },
        ),
    },
)
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
