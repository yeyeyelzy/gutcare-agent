"""Request correlation middleware."""

from time import perf_counter
from uuid import UUID, uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

from gutcare.shared.metrics import OperationsMetrics


class RequestIdMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        service_name: str = "gutcare-business-api",
        metrics: OperationsMetrics | None = None,
    ) -> None:
        self.app = app
        self.service_name = service_name
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = (
            dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("ascii", "ignore")
        )
        try:
            request_id = str(UUID(supplied))
        except (ValueError, AttributeError):
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        clear_contextvars()
        bind_contextvars(request_id=request_id, service=self.service_name)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            duration_seconds = perf_counter() - started_at
            if self.metrics is not None and route_path != "/ops/metrics":
                self.metrics.observe_request(
                    str(scope.get("method", "OTHER")), route_path, status_code, duration_seconds
                )
            structlog.get_logger().info(
                "http_request",
                service=self.service_name,
                request_id=request_id,
                route=route_path,
                status_code=status_code,
                duration_ms=round(duration_seconds * 1000, 2),
            )
            clear_contextvars()
