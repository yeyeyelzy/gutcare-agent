"""Frozen F14 mood-record API."""

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from gutcare.auth.api import current_auth_context, problem_response
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")
MoodTag = Literal[
    "calm", "content", "joyful", "sad", "anxious", "irritable", "overwhelmed", "tired", "other"
]


class MoodServicePort(Protocol):
    def create(
        self, context: AuthContext, data: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]: ...
    def list(
        self,
        context: AuthContext,
        *,
        cursor: str | None,
        limit: int,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]: ...
    def get(self, context: AuthContext, record_id: UUID) -> dict[str, Any]: ...
    def patch(
        self, context: AuthContext, record_id: UUID, version: int, changes: dict[str, Any]
    ) -> dict[str, Any]: ...
    def delete(self, context: AuthContext, record_id: UUID, version: int) -> None: ...


class MoodWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: datetime
    mood_level: StrictInt = Field(ge=1, le=5)
    emotion_tags: list[MoodTag] = Field(
        default_factory=list, max_length=5, json_schema_extra={"uniqueItems": True}
    )
    note: str | None = Field(default=None, max_length=500)

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("emotion_tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("emotion_tags must be unique")
        return value


class MoodPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: StrictInt = Field(ge=1)
    occurred_at: datetime | None = Field(
        default=None,
        json_schema_extra={"anyOf": [{"type": "string", "format": "date-time"}]},
    )
    mood_level: StrictInt | None = Field(
        default=None,
        ge=1,
        le=5,
        json_schema_extra={"anyOf": [{"type": "integer", "minimum": 1, "maximum": 5}]},
    )
    emotion_tags: list[MoodTag] | None = Field(
        default=None,
        max_length=5,
        json_schema_extra={
            "anyOf": [
                {
                    "type": "array",
                    "maxItems": 5,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "enum": [
                            "calm",
                            "content",
                            "joyful",
                            "sad",
                            "anxious",
                            "irritable",
                            "overwhelmed",
                            "tired",
                            "other",
                        ],
                    },
                }
            ]
        },
    )
    note: str | None = Field(default=None, max_length=500)

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("emotion_tags")
    @classmethod
    def unique_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("emotion_tags must be unique")
        return value

    @model_validator(mode="after")
    def non_null_values(self) -> "MoodPatch":
        for field in ("occurred_at", "mood_level", "emotion_tags"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MoodDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: StrictInt = Field(ge=1)


class MoodSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    occurred_at: datetime
    mood_level: int
    emotion_tags: list[MoodTag]
    record_version: int
    created_at: datetime
    updated_at: datetime


class MoodDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    occurred_at: datetime
    mood_level: int
    emotion_tags: list[MoodTag]
    record_version: int
    created_at: datetime
    updated_at: datetime
    note: str | None


class MoodPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MoodSummary]
    next_cursor: str | None


def get_mood_service(request: Request) -> MoodServicePort:
    service = cast(MoodServicePort | None, request.app.state.mood_service)
    if service is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return service


COMMON = {
    401: problem_response("访问令牌无效或缺失"),
    404: problem_response("资源不存在"),
    409: problem_response("记录冲突或缺少授权"),
    422: problem_response("请求字段无效"),
}


@router.get(
    "/mood-records",
    operation_id="listMoodRecords",
    response_model=MoodPage,
    tags=["Records"],
    responses={401: COMMON[401], 422: COMMON[422]},
)
def list_mood_records(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[MoodServicePort, Depends(get_mood_service)],
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    return service.list(context, cursor=cursor, limit=limit, since=since, until=until)


@router.post(
    "/mood-records",
    operation_id="createMoodRecord",
    status_code=status.HTTP_201_CREATED,
    response_model=MoodDetail,
    tags=["Records"],
    responses={401: COMMON[401], 409: COMMON[409], 422: COMMON[422]},
)
def create_mood_record(
    body: MoodWrite,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[MoodServicePort, Depends(get_mood_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    return service.create(context, body.model_dump(), idempotency_key)


@router.get(
    "/mood-records/{record_id}",
    operation_id="getMoodRecord",
    response_model=MoodDetail,
    tags=["Records"],
    responses={401: COMMON[401], 404: COMMON[404], 422: COMMON[422]},
)
def get_mood_record(
    record_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[MoodServicePort, Depends(get_mood_service)],
) -> dict[str, Any]:
    return service.get(context, record_id)


@router.patch(
    "/mood-records/{record_id}",
    operation_id="patchMoodRecord",
    response_model=MoodDetail,
    tags=["Records"],
    responses={401: COMMON[401], 404: COMMON[404], 409: COMMON[409], 422: COMMON[422]},
)
def patch_mood_record(
    record_id: UUID,
    body: MoodPatch,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[MoodServicePort, Depends(get_mood_service)],
) -> dict[str, Any]:
    values = body.model_dump(exclude={"record_version"}, exclude_unset=True)
    return service.patch(context, record_id, body.record_version, values)


@router.delete(
    "/mood-records/{record_id}",
    operation_id="deleteMoodRecord",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    tags=["Records"],
    responses={401: COMMON[401], 404: COMMON[404], 409: COMMON[409], 422: COMMON[422]},
)
def delete_mood_record(
    record_id: UUID,
    body: MoodDelete,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[MoodServicePort, Depends(get_mood_service)],
) -> Response:
    service.delete(context, record_id, body.record_version)
    return Response(status_code=204)
