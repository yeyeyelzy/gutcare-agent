"""F12 notification patient APIs."""

from datetime import time
from typing import Annotated, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


class PreferenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinary_in_app_enabled: bool
    quiet_start: time | None = None
    quiet_end: time | None = None
    timezone: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def quiet_pair(self) -> "PreferenceBody":
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("quiet hours require both endpoints")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("timezone must be a valid IANA timezone") from None
        return self


class BatchReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notification_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> "BatchReadBody":
        if len(self.notification_ids) != len(set(self.notification_ids)):
            raise ValueError("notification_ids must be unique")
        return self


class Service(Protocol):
    def list_notifications(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        category: str | None,
        unread_only: bool,
    ) -> dict[str, object]: ...
    def get(self, context: AuthContext, ident: UUID) -> dict[str, object]: ...
    def unread_count(self, context: AuthContext) -> dict[str, int]: ...
    def mark_read(self, context: AuthContext, ident: UUID) -> dict[str, object]: ...
    def mark_many(self, context: AuthContext, ids: list[UUID]) -> list[dict[str, object]]: ...
    def get_preferences(self, context: AuthContext) -> dict[str, object]: ...
    def set_preferences(
        self, context: AuthContext, payload: dict[str, object]
    ) -> dict[str, object]: ...


def _service(request: Request) -> Service:
    service = getattr(request.app.state, "notification_service", None)
    if service is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Notification service unavailable")
    return cast(Service, service)


@router.get("")
def list_notifications(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=128),
    category: str | None = Query(None, pattern="^(analysis|advice|risk|medication_reminder)$"),
    unread_only: bool = False,
) -> dict[str, object]:
    return svc.list_notifications(context, limit, cursor, category, unread_only)


@router.get("/unread-count")
def unread_count(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, int]:
    return svc.unread_count(context)


@router.get("/preferences")
def get_preferences(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, object]:
    return svc.get_preferences(context)


@router.put("/preferences")
def set_preferences(
    body: PreferenceBody,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, object]:
    return svc.set_preferences(context, body.model_dump())


@router.post("/read-batch")
def read_batch(
    body: BatchReadBody,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, object]:
    return {"items": svc.mark_many(context, body.notification_ids)}


@router.get("/{notification_id}")
def get_notification(
    notification_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, object]:
    return svc.get(context, notification_id)


@router.post("/{notification_id}/read")
def read_notification(
    notification_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, object]:
    return svc.mark_read(context, notification_id)
