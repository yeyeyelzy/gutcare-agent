"""Patient-facing privacy controls and receipt-only deletion status."""

from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")
_status_attempts: dict[str, deque[float]] = defaultdict(deque)
_status_attempts_lock = Lock()


def _limit_status_checks(client_key: str) -> None:
    now = monotonic()
    with _status_attempts_lock:
        attempts = _status_attempts[client_key]
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 20:
            raise Problem(429, "RATE_LIMITED", "Status query rate limit exceeded")
        attempts.append(now)


def _iso_date(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


class PrivacyServicePort(Protocol):
    def request_deletion(self, context: AuthContext) -> tuple[UUID, str | None]: ...
    def deletion_status(self, operation_id: UUID, receipt: str) -> dict[str, object]: ...
    def create_export_preview(
        self, context: AuthContext, categories: list[str]
    ) -> tuple[UUID, list[str]]: ...
    def confirm_export(self, context: AuthContext, export_id: UUID) -> None: ...
    def cancel_export(self, context: AuthContext, export_id: UUID) -> None: ...
    def export_status(self, context: AuthContext, export_id: UUID) -> dict[str, object]: ...
    def list_exports(self, context: AuthContext) -> list[dict[str, object]]: ...
    def download_export(self, capability: str) -> bytes: ...


def get_privacy_service(request: Request) -> PrivacyServicePort:
    service: PrivacyServicePort | None = request.app.state.privacy_service
    if service is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Privacy service unavailable")
    return service


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeleteResponse(BaseModel):
    operation_id: UUID
    receipt: str | None = None
    status: str = "accepted"


class DeleteStatus(BaseModel):
    operation_id: UUID
    status: str
    requested_at: str
    due_at: str
    completed_at: str | None


class ReceiptQuery(BaseModel):
    receipt: str = Field(min_length=40, max_length=128)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: list[str] = Field(min_length=1, max_length=16)


class ExportResponse(BaseModel):
    export_id: UUID
    categories: list[str]
    status: str


class ExportStatusResponse(BaseModel):
    export_id: UUID
    status: str
    categories: list[str]
    expires_at: str | None
    download_capability: str | None = None


@router.post(
    "/patients/me/account-deletion",
    operation_id="requestAccountDeletion",
    summary="启动注销并获取一次性进度凭据",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DeleteResponse,
    responses={
        401: {"description": "需要有效会话"},
        404: {"description": "账户不存在"},
        409: {"description": "注销操作已存在"},
    },
    tags=["Privacy"],
)
def request_deletion(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> DeleteResponse:
    operation_id, receipt = service.request_deletion(context)
    return DeleteResponse(operation_id=operation_id, receipt=receipt)


@router.post(
    "/privacy/deletion-operations/{operation_id}/status",
    response_model=DeleteStatus,
    responses={404: {"description": "操作或 receipt 不存在"}, 429: {"description": "查询频率受限"}},
    tags=["Privacy"],
)
def deletion_status(
    operation_id: UUID,
    body: ReceiptQuery,
    request: Request,
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> DeleteStatus:
    _limit_status_checks(request.client.host if request.client else "unknown")
    result = service.deletion_status(operation_id, body.receipt)
    requested_at = result["requested_at"]
    due_at = result["due_at"]
    completed_at = result["completed_at"]
    assert isinstance(requested_at, datetime) and isinstance(due_at, datetime)
    assert completed_at is None or isinstance(completed_at, datetime)
    return DeleteStatus(
        operation_id=operation_id,
        status=str(result["status"]),
        requested_at=requested_at.isoformat(),
        due_at=due_at.isoformat(),
        completed_at=completed_at.isoformat() if completed_at else None,
    )


@router.post(
    "/privacy/exports",
    status_code=status.HTTP_201_CREATED,
    response_model=ExportResponse,
    responses={401: {"description": "需要有效会话"}, 422: {"description": "导出类别无效"}},
    tags=["Privacy"],
)
def create_export(
    body: ExportRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> ExportResponse:
    export_id, categories = service.create_export_preview(context, body.categories)
    return ExportResponse(export_id=export_id, categories=categories, status="preview")


@router.get("/privacy/exports", response_model=list[ExportStatusResponse], tags=["Privacy"])
def list_exports(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> list[ExportStatusResponse]:
    rows = service.list_exports(context)
    return [
        ExportStatusResponse(
            export_id=cast(UUID, row["export_id"]),
            status=str(row["status"]),
            categories=list(cast(list[str], row["categories"])),
            expires_at=_iso_date(row["expires_at"]),
        )
        for row in rows
    ]


@router.get(
    "/privacy/exports/{export_id}",
    response_model=ExportStatusResponse,
    tags=["Privacy"],
)
def export_status(
    export_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> ExportStatusResponse:
    row = service.export_status(context, export_id)
    expiry = cast(datetime | None, row["expires_at"])
    return ExportStatusResponse(
        export_id=export_id,
        status=str(row["status"]),
        categories=list(cast(list[str], row["categories"])),
        expires_at=_iso_date(expiry),
        download_capability=(
            str(row["download_capability"]) if row["download_capability"] else None
        ),
    )


@router.post(
    "/privacy/exports/{export_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    responses={
        401: {"description": "需要有效会话"},
        404: {"description": "导出不存在"},
        409: {"description": "导出状态冲突"},
    },
    tags=["Privacy"],
)
def confirm_export(
    export_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> None:
    service.confirm_export(context, export_id)


@router.post(
    "/privacy/exports/{export_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={401: {"description": "需要有效会话"}, 404: {"description": "导出不存在"}},
    tags=["Privacy"],
)
def cancel_export(
    export_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> None:
    service.cancel_export(context, export_id)


@router.get(
    "/privacy/exports/download",
    response_model=None,
    include_in_schema=True,
    tags=["Privacy"],
)
def download_export(
    capability: Annotated[str, Header(alias="X-Export-Capability", min_length=40, max_length=128)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> Response | StreamingResponse:
    content = service.download_export(capability)
    return StreamingResponse(
        (content[offset : offset + 64 * 1024] for offset in range(0, len(content), 64 * 1024)),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="gutcare-export.zip"'},
    )
