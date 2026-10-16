"""RFC 9457 Problem Details error responses."""

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class Problem(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str = "",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        super().__init__(detail or title)


def _request_id(request: Request) -> str:
    raw_id = getattr(request.state, "request_id", None)
    try:
        return str(UUID(raw_id))
    except (ValueError, TypeError, AttributeError):
        return str(UUID(int=0))


def _problem_response(request: Request, problem: Problem) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://gutcare.invalid/problems/{problem.code.lower()}",
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "instance": request.url.path,
        "code": problem.code,
        "request_id": _request_id(request),
    }
    if problem.errors is not None:
        body["errors"] = problem.errors
    return JSONResponse(body, status_code=problem.status, media_type="application/problem+json")


def install_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(Problem)
    async def handle_problem(request: Request, exc: Problem) -> JSONResponse:
        return _problem_response(request, exc)

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"location": list(item["loc"]), "code": item["type"], "message": item["msg"]}
            for item in exc.errors()
        ]
        return _problem_response(
            request,
            Problem(422, "VALIDATION_ERROR", "Request validation failed", errors=errors),
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        titles = {404: "Not found", 405: "Method not allowed"}
        return _problem_response(
            request,
            Problem(
                exc.status_code,
                f"HTTP_{exc.status_code}",
                titles.get(exc.status_code, "Request failed"),
            ),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, _: Exception) -> JSONResponse:
        return _problem_response(
            request,
            Problem(500, "INTERNAL_ERROR", "Internal server error"),
        )
