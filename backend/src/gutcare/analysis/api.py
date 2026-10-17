"""F08 patient and service-to-service API."""

import hmac
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gutcare.auth.api import current_auth_context, problem_response
from gutcare.auth.service import AuthContext
from gutcare.shared.errors import Problem


def validate_analysis_range(
    analysis_type: str, requested_from: datetime | None, requested_to: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if requested_from is not None and requested_from.tzinfo is None:
        raise ValueError("requested_from must include timezone")
    if requested_to is not None and requested_to.tzinfo is None:
        raise ValueError("requested_to must include timezone")
    if (requested_from is None) != (requested_to is None):
        raise ValueError("requested_from and requested_to must be provided together")
    if requested_from is not None and requested_to is not None and requested_from >= requested_to:
        raise ValueError("requested_from must be earlier than requested_to")
    if analysis_type == "periodic_summary" and requested_from is None:
        raise ValueError("periodic_summary requires an explicit time range")
    if requested_from is not None:
        requested_from = requested_from.astimezone(UTC)
        requested_to = requested_to.astimezone(UTC) if requested_to is not None else None
    return requested_from, requested_to


router = APIRouter(prefix="/api/v1")
agent_router = APIRouter(prefix="/internal/v1/agent")


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_type: Literal["comprehensive_health_analysis", "periodic_summary"]
    requested_from: datetime | None = None
    requested_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "TaskCreate":
        self.requested_from, self.requested_to = validate_analysis_range(
            self.analysis_type, self.requested_from, self.requested_to
        )
        return self


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisInputSummary(Strict):
    included_mood_record_count: int = Field(ge=0)


class AnalysisResultEvidence(Strict):
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


class AnalysisResult(Strict):
    schema_version: Literal["1.0"]
    summary: str = Field(max_length=1200)
    observations: list[Annotated[str, Field(max_length=500)]] = Field(max_length=30)
    evidence: list[AnalysisResultEvidence] = Field(max_length=100)
    uncertainties: list[Annotated[str, Field(max_length=500)]] = Field(max_length=30)
    missing_data: list[Annotated[str, Field(max_length=120)]] = Field(max_length=30)


class AnalysisTask(Strict):
    id: UUID
    analysis_type: Literal["comprehensive_health_analysis", "periodic_summary"]
    status: Literal[
        "pending", "processing", "needs_input", "succeeded", "partial", "failed", "cancelled"
    ]
    input_summary: AnalysisInputSummary
    created_at: datetime
    updated_at: datetime
    attempt: int = Field(ge=1)
    retry_of: UUID | None
    result: AnalysisResult | None
    error_code: str | None = Field(pattern=r"^[A-Z0-9_]+$")


class AnalysisTaskPage(Strict):
    items: list[AnalysisTask]
    next_cursor: str | None


class AnalysisTaskPreview(Strict):
    analysis_type: Literal["comprehensive_health_analysis", "periodic_summary"]
    requested_from: datetime | None
    requested_to: datetime | None
    timezone: str = Field(min_length=1, max_length=64)
    mood_record_count_in_range: int = Field(ge=0)
    mood_record_count_eligible: int = Field(ge=0)
    mood_record_count_excluded_by_consent: int = Field(ge=0)
    mood_exclusion_reasons: list[Literal["mood_data_processing_missing", "mood_ai_sharing_missing"]]


def _problem(status: int, code: str, detail: str, instance: str) -> dict[str, Any]:
    return {
        "type": f"https://gutcare.invalid/problems/{code.lower()}",
        "title": "Request failed" if status != 422 else "Request validation failed",
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": code,
        "request_id": f"00000000-0000-4000-8000-{status:012d}",
    }


def _patient_problem_responses(
    path: str, statuses: tuple[int, ...]
) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        400: ("INVALID_CURSOR", "Analysis task cursor is invalid"),
        401: ("AUTHENTICATION_REQUIRED", "Authentication required"),
        404: ("RESOURCE_NOT_FOUND", "Resource not found"),
        409: ("TASK_STATE_CONFLICT", "Analysis task state or authorization conflict"),
        422: ("VALIDATION_ERROR", "Request validation failed"),
        500: ("INTERNAL_ERROR", "Service temporarily unavailable"),
    }
    return {
        status: problem_response(
            descriptions[status][1],
            _problem(status, descriptions[status][0], descriptions[status][1], path),
        )
        for status in statuses
    }


def _analysis_task_example(
    *, status: str = "pending", attempt: int = 1, retry_of: str | None = None
) -> dict[str, Any]:
    return {
        "id": "019a0000-0000-7000-8000-000000000801",
        "analysis_type": "comprehensive_health_analysis",
        "status": status,
        "input_summary": {"included_mood_record_count": 0},
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        "attempt": attempt,
        "retry_of": retry_of,
        "result": None,
        "error_code": None,
    }


def _analysis_success_response(
    status: int, schema: str, description: str, example: dict[str, Any]
) -> dict[int | str, dict[str, Any]]:
    response: dict[str, Any] = {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{schema}"},
                "examples": {"example": {"value": example}},
            }
        },
    }
    if status == 202:
        response["headers"] = {
            "Location": {
                "description": "新建任务资源地址",
                "schema": {"type": "string", "format": "uri-reference"},
            }
        }
    return {status: response}


class ResultEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    status: Literal["succeeded", "partial", "needs_input"]
    schema_version: Literal["1.0"]
    summary: str = Field(max_length=1200)
    observations: list[Annotated[str, Field(strict=True, max_length=500)]] = Field(max_length=30)
    evidence: list[ResultEvidence] = Field(max_length=100)
    uncertainties: list[Annotated[str, Field(strict=True, max_length=500)]] = Field(max_length=30)
    missing_data: list[Annotated[str, Field(strict=True, max_length=120)]] = Field(max_length=30)


class Failure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    error_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")


class Service(Protocol):
    def preview(
        self,
        context: AuthContext,
        analysis_type: str,
        requested_from: datetime | None,
        requested_to: datetime | None,
    ) -> dict[str, Any]: ...
    def create(
        self, context: AuthContext, payload: dict[str, Any], key: str
    ) -> tuple[dict[str, Any], bool]: ...
    def get(self, context: AuthContext, task_id: UUID) -> dict[str, Any]: ...
    def list(
        self, context: AuthContext, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]: ...
    def cancel(self, context: AuthContext, task_id: UUID) -> dict[str, Any]: ...
    def retry(
        self, context: AuthContext, task_id: UUID, key: str
    ) -> tuple[dict[str, Any], bool]: ...
    def claim(self) -> dict[str, Any] | None: ...
    def inputs(self, task_id: UUID) -> dict[str, Any]: ...
    def result(self, task_id: UUID, callback_id: UUID, payload: dict[str, Any]) -> None: ...
    def fail(self, task_id: UUID, callback_id: UUID, error_code: str) -> None: ...


def _service(request: Request) -> Service:
    result = getattr(request.app.state, "analysis_service", None)
    if result is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return cast(Service, result)


def _worker_service(request: Request) -> Service:
    result = getattr(request.app.state, "analysis_worker_service", None)
    if result is None:
        raise Problem(503, "SERVICE_UNAVAILABLE", "Analysis worker is unavailable")
    return cast(Service, result)


def _agent(request: Request, authorization: str | None) -> None:
    token = request.app.state.settings.agent_service_token
    if (
        not token
        or not authorization
        or not authorization.startswith("Bearer ")
        or not hmac.compare_digest(authorization[7:], token)
    ):
        raise Problem(401, "AUTHENTICATION_REQUIRED", "Service authentication required")


@router.get(
    "/analysis-tasks/preview",
    operation_id="previewAnalysisTask",
    response_model=AnalysisTaskPreview,
    responses={
        **_analysis_success_response(
            200,
            "AnalysisTaskPreview",
            "当前范围的心情输入预览；不构成最终冻结快照",
            {
                "analysis_type": "periodic_summary",
                "requested_from": "2026-10-01T00:00:00Z",
                "requested_to": "2026-10-08T00:00:00Z",
                "timezone": "Asia/Shanghai",
                "mood_record_count_in_range": 3,
                "mood_record_count_eligible": 2,
                "mood_record_count_excluded_by_consent": 1,
                "mood_exclusion_reasons": ["mood_ai_sharing_missing"],
            },
        ),
        **_patient_problem_responses("/api/v1/analysis-tasks/preview", (401, 404, 409, 422, 500)),
    },
)
def preview_task(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
    analysis_type: Literal["comprehensive_health_analysis", "periodic_summary"],
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
) -> dict[str, Any]:
    try:
        requested_from, requested_to = validate_analysis_range(
            analysis_type, requested_from, requested_to
        )
    except ValueError as exc:
        raise Problem(422, "VALIDATION_ERROR", str(exc)) from exc
    return svc.preview(context, analysis_type, requested_from, requested_to)


@router.post(
    "/analysis-tasks",
    status_code=202,
    operation_id="createAnalysisTask",
    response_model=AnalysisTask,
    responses={
        **_analysis_success_response(
            202, "AnalysisTask", "异步任务已受理并返回不可变输入摘要", _analysis_task_example()
        ),
        **_patient_problem_responses("/api/v1/analysis-tasks", (401, 404, 409, 422, 500)),
    },
)
def create_task(
    body: TaskCreate,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> Response:
    dto, replay = svc.create(context, body.model_dump(mode="json"), key)
    validated = AnalysisTask.model_validate(dto)
    return Response(
        content=__import__("json").dumps(validated.model_dump(mode="json")),
        status_code=202,
        media_type="application/json",
        headers={"Location": f"{request.url.path}/{dto['id']}"},
    )


@router.get(
    "/analysis-tasks",
    operation_id="listAnalysisTasks",
    response_model=AnalysisTaskPage,
    responses={
        **_analysis_success_response(
            200,
            "AnalysisTaskPage",
            "当前患者分析任务的稳定游标分页",
            {"items": [_analysis_task_example()], "next_cursor": None},
        ),
        **_patient_problem_responses("/api/v1/analysis-tasks", (400, 401, 404, 422, 500)),
    },
)
def list_tasks(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, min_length=1, max_length=512),
) -> dict[str, Any]:
    return svc.list(context, limit, cursor)


@router.get(
    "/analysis-tasks/{task_id}",
    operation_id="getAnalysisTask",
    response_model=AnalysisTask,
    responses={
        **_analysis_success_response(
            200, "AnalysisTask", "本人任务状态与受控摘要", _analysis_task_example()
        ),
        **_patient_problem_responses("/api/v1/analysis-tasks/{task_id}", (401, 404, 422, 500)),
    },
)
def get_task(
    task_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, Any]:
    return svc.get(context, task_id)


@router.post(
    "/analysis-tasks/{task_id}/cancel",
    operation_id="cancelAnalysisTask",
    response_model=AnalysisTask,
    responses={
        **_analysis_success_response(
            200,
            "AnalysisTask",
            "已取消的分析任务",
            _analysis_task_example(status="cancelled"),
        ),
        **_patient_problem_responses(
            "/api/v1/analysis-tasks/{task_id}/cancel", (401, 404, 409, 422, 500)
        ),
    },
)
def cancel_task(
    task_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
) -> dict[str, Any]:
    return svc.cancel(context, task_id)


@router.post(
    "/analysis-tasks/{task_id}/retry",
    status_code=202,
    operation_id="retryAnalysisTask",
    response_model=AnalysisTask,
    responses={
        **_analysis_success_response(
            202,
            "AnalysisTask",
            "从原不可变快照创建的新尝试",
            _analysis_task_example(attempt=2, retry_of="019a0000-0000-7000-8000-000000000802"),
        ),
        **_patient_problem_responses(
            "/api/v1/analysis-tasks/{task_id}/retry", (401, 404, 409, 422, 500)
        ),
    },
)
def retry_task(
    task_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    svc: Annotated[Service, Depends(_service)],
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> Response:
    dto, _ = svc.retry(context, task_id, key)
    validated = AnalysisTask.model_validate(dto)
    return Response(
        content=__import__("json").dumps(validated.model_dump(mode="json")),
        status_code=202,
        media_type="application/json",
        headers={"Location": f"/api/v1/analysis-tasks/{dto['id']}"},
    )


@agent_router.post("/analysis-tasks/claim", operation_id="claimAnalysisTask")
def claim(
    request: Request,
    svc: Annotated[Service, Depends(_worker_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _agent(request, authorization)
    return {"task": svc.claim()}


@agent_router.get("/analysis-tasks/{task_id}/inputs", operation_id="getAnalysisTaskInputs")
def inputs(
    task_id: UUID,
    request: Request,
    svc: Annotated[Service, Depends(_worker_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _agent(request, authorization)
    return svc.inputs(task_id)


@agent_router.post(
    "/analysis-tasks/{task_id}/result", status_code=204, operation_id="submitAnalysisResult"
)
def result(
    task_id: UUID,
    body: AgentResult,
    request: Request,
    svc: Annotated[Service, Depends(_worker_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _agent(request, authorization)
    svc.result(task_id, body.callback_id, body.model_dump(mode="json"))
    return Response(status_code=204)


@agent_router.post(
    "/analysis-tasks/{task_id}/fail", status_code=204, operation_id="failAnalysisTask"
)
def fail(
    task_id: UUID,
    body: Failure,
    request: Request,
    svc: Annotated[Service, Depends(_worker_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _agent(request, authorization)
    svc.fail(task_id, body.callback_id, body.error_code)
    return Response(status_code=204)
