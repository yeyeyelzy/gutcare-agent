"""Patient-facing privacy controls and receipt-only deletion status."""

from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from gutcare.auth.api import current_auth_context, problem_response
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
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    receipt: str | None = None
    status: Literal["accepted"] = "accepted"


class DeleteStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    status: Literal["pending", "processing", "overdue", "dead_letter", "completed"]
    requested_at: datetime
    due_at: datetime
    completed_at: datetime | None


class ReceiptQuery(BaseModel):
    receipt: str = Field(min_length=40, max_length=128)


ExportCategory = Literal[
    "profile",
    "consents",
    "medical_documents",
    "files",
    "diet",
    "stool",
    "symptoms",
    "mood",
    "medication",
    "activity",
    "analysis",
    "advice",
    "alerts",
    "notifications",
]
ExportStatus = Literal[
    "preview", "pending", "processing", "ready", "failed", "cancelled", "expired"
]


class ExportRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"categories": ["profile", "consents"]}]}
    )
    categories: list[ExportCategory] = Field(min_length=1, max_length=16)


class ExportResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "export_id": "019a0000-0000-7000-8000-000000000201",
                    "categories": ["profile", "consents"],
                    "status": "preview",
                }
            ]
        },
    )

    export_id: UUID
    categories: list[ExportCategory]
    status: Literal["preview"]


class ExportSummaryResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "export_id": "019a0000-0000-7000-8000-000000000201",
                    "status": "pending",
                    "categories": ["profile", "consents"],
                    "created_at": "2026-10-18T08:30:00Z",
                    "expires_at": None,
                }
            ]
        },
    )

    export_id: UUID
    status: ExportStatus
    categories: list[ExportCategory]
    created_at: datetime
    expires_at: datetime | None


class ExportStatusResponse(ExportSummaryResponse):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "export_id": "019a0000-0000-7000-8000-000000000201",
                    "status": "ready",
                    "categories": ["profile", "consents"],
                    "created_at": "2026-10-18T08:30:00Z",
                    "expires_at": "2026-10-19T08:30:00Z",
                    "download_capability": (
                        "example-only-capability-not-valid-"
                        "0000000000000000000000000000000000000000000000000000000000000000"
                    ),
                }
            ]
        },
    )
    download_capability: str | None = None


def _export_problem(
    status_code: int,
    code: str,
    title: str,
    description: str,
    *,
    instance: str = "/api/v1/privacy/exports",
) -> dict[str, object]:
    return problem_response(
        description,
        {
            "type": f"https://gutcare.invalid/problems/{code.lower()}",
            "title": title,
            "status": status_code,
            "detail": description,
            "instance": instance,
            "code": code,
            "request_id": f"00000000-0000-4000-8000-000000000{status_code}",
        },
    )


@router.post(
    "/patients/me/account-deletion",
    operation_id="requestAccountDeletion",
    summary="启动注销并获取一次性进度凭据",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DeleteResponse,
    responses={
        202: {
            "description": (
                "账户立即冻结并撤销 refresh session。仅首次创建返回一次性 receipt；"
                "重试复用 operation 且 receipt 为 null。"
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "firstAcceptance": {
                            "summary": "首次受理（receipt 仅本次响应可见）",
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "receipt": "one-time-high-entropy-value-0123456789-abcdef",
                                "status": "accepted",
                            },
                        },
                        "idempotentRetry": {
                            "summary": "同一活动操作的重试（不重新发放 receipt）",
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "receipt": None,
                                "status": "accepted",
                            },
                        },
                    }
                }
            },
        },
        401: problem_response("需要有效会话"),
        404: problem_response(
            "账户或本人资料不可用",
            {
                "type": "about:blank",
                "title": "Not found",
                "status": 404,
                "code": "RESOURCE_NOT_FOUND",
                "request_id": "00000000-0000-4000-8000-000000000404",
            },
        ),
        500: problem_response(
            "注销请求暂不可用",
            {
                "type": "about:blank",
                "title": "Internal server error",
                "status": 500,
                "code": "INTERNAL_ERROR",
                "request_id": "00000000-0000-4000-8000-000000000500",
            },
        ),
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
    operation_id="getPrivacyDeletionStatus",
    response_model=DeleteStatus,
    responses={
        200: {
            "description": "使用 operation_id 与请求体中的 receipt 查询；不需要登录。",
            "content": {
                "application/json": {
                    "examples": {
                        "pending": {
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "status": "pending",
                                "requested_at": "2026-10-17T12:00:00Z",
                                "due_at": "2026-11-16T12:00:00Z",
                                "completed_at": None,
                            }
                        },
                        "processing": {
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "status": "processing",
                                "requested_at": "2026-10-17T12:00:00Z",
                                "due_at": "2026-11-16T12:00:00Z",
                                "completed_at": None,
                            }
                        },
                        "overdue": {
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "status": "overdue",
                                "requested_at": "2026-10-17T12:00:00Z",
                                "due_at": "2026-11-16T12:00:00Z",
                                "completed_at": None,
                            }
                        },
                        "deadLetter": {
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "status": "dead_letter",
                                "requested_at": "2026-10-17T12:00:00Z",
                                "due_at": "2026-11-16T12:00:00Z",
                                "completed_at": None,
                            }
                        },
                        "completed": {
                            "value": {
                                "operation_id": "019a0000-0000-7000-8000-000000000020",
                                "status": "completed",
                                "requested_at": "2026-10-17T12:00:00Z",
                                "due_at": "2026-11-16T12:00:00Z",
                                "completed_at": "2026-10-18T12:00:00Z",
                            }
                        },
                    }
                }
            },
        },
        404: problem_response(
            "操作或 receipt 不存在，统一返回不可用响应",
            {
                "type": "about:blank",
                "title": "Not found",
                "status": 404,
                "code": "RESOURCE_NOT_FOUND",
                "request_id": "00000000-0000-4000-8000-000000000404",
            },
        ),
        422: problem_response(
            "operation_id 或 receipt 格式无效",
            {
                "type": "about:blank",
                "title": "Request validation failed",
                "status": 422,
                "code": "VALIDATION_ERROR",
                "request_id": "00000000-0000-4000-8000-000000000422",
            },
        ),
        429: problem_response(
            "查询频率受限",
            {
                "type": "about:blank",
                "title": "Status query rate limit exceeded",
                "status": 429,
                "code": "RATE_LIMITED",
                "request_id": "00000000-0000-4000-8000-000000000429",
            },
        ),
        503: problem_response(
            "隐私服务暂不可用",
            {
                "type": "about:blank",
                "title": "Service unavailable",
                "status": 503,
                "code": "SERVICE_UNAVAILABLE",
                "request_id": "00000000-0000-4000-8000-000000000503",
            },
        ),
    },
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
        status=cast(
            Literal["pending", "processing", "overdue", "dead_letter", "completed"],
            result["status"],
        ),
        requested_at=requested_at,
        due_at=due_at,
        completed_at=completed_at,
    )


@router.post(
    "/privacy/exports",
    operation_id="createPrivacyExport",
    status_code=status.HTTP_201_CREATED,
    response_model=ExportResponse,
    responses={
        401: _export_problem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "需要有效会话"
        ),
        422: _export_problem(
            422, "VALIDATION_ERROR", "Request validation failed", "导出类别为空或不受支持。"
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "加密导出暂不可用。"
        ),
    },
    tags=["Privacy"],
)
def create_export(
    body: ExportRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> ExportResponse:
    export_id, categories = service.create_export_preview(context, cast(list[str], body.categories))
    return ExportResponse(
        export_id=export_id, categories=cast(list[ExportCategory], categories), status="preview"
    )


@router.get(
    "/privacy/exports",
    operation_id="listPrivacyExports",
    response_model=list[ExportSummaryResponse],
    responses={
        401: _export_problem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "需要有效会话"
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "隐私服务暂不可用。"
        ),
    },
    tags=["Privacy"],
)
def list_exports(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[PrivacyServicePort, Depends(get_privacy_service)],
) -> list[ExportSummaryResponse]:
    rows = service.list_exports(context)
    return [
        ExportSummaryResponse(
            export_id=cast(UUID, row["export_id"]),
            status=cast(ExportStatus, str(row["status"])),
            categories=list(cast(list[ExportCategory], row["categories"])),
            created_at=cast(datetime, row["created_at"]),
            expires_at=cast(datetime | None, row["expires_at"]),
        )
        for row in rows
    ]


@router.get(
    "/privacy/exports/{export_id}",
    operation_id="getPrivacyExport",
    response_model=ExportStatusResponse,
    responses={
        401: _export_problem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "需要有效会话"
        ),
        404: _export_problem(404, "RESOURCE_NOT_FOUND", "Not found", "本人导出不存在。"),
        422: _export_problem(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            "导出 ID 格式无效。",
            instance="/api/v1/privacy/exports/not-a-uuid",
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "隐私服务暂不可用。"
        ),
    },
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
        status=cast(ExportStatus, str(row["status"])),
        categories=list(cast(list[ExportCategory], row["categories"])),
        created_at=cast(datetime, row["created_at"]),
        expires_at=expiry,
        download_capability=(
            str(row["download_capability"]) if row["download_capability"] else None
        ),
    )


@router.post(
    "/privacy/exports/{export_id}",
    operation_id="confirmPrivacyExport",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    responses={
        401: _export_problem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "需要有效会话"
        ),
        404: _export_problem(404, "RESOURCE_NOT_FOUND", "Not found", "本人导出不存在。"),
        422: _export_problem(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            "导出 ID 格式无效。",
            instance="/api/v1/privacy/exports/not-a-uuid",
        ),
        409: _export_problem(
            409, "IDEMPOTENCY_CONFLICT", "Export state conflict", "导出状态不允许确认。"
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "加密导出暂不可用。"
        ),
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
    operation_id="cancelPrivacyExport",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        401: _export_problem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "需要有效会话"
        ),
        404: _export_problem(404, "RESOURCE_NOT_FOUND", "Not found", "本人导出不存在。"),
        422: _export_problem(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            "导出 ID 格式无效。",
            instance="/api/v1/privacy/exports/not-a-uuid",
        ),
        409: _export_problem(
            409, "IDEMPOTENCY_CONFLICT", "Export state conflict", "该导出状态不允许取消。"
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "隐私服务暂不可用。"
        ),
    },
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
    operation_id="downloadPrivacyExport",
    response_model=None,
    responses={
        200: {
            "description": "五分钟单次能力对应的 ZIP 流。",
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        },
        404: _export_problem(404, "RESOURCE_NOT_FOUND", "Not found", "下载能力不可用或已使用。"),
        422: _export_problem(
            422, "VALIDATION_ERROR", "Request validation failed", "下载 header 格式无效。"
        ),
        503: _export_problem(
            503, "SERVICE_UNAVAILABLE", "Service unavailable", "导出下载暂不可用。"
        ),
    },
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
