"""Structured logging setup with sensitive-field redaction."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEYS = re.compile(
    r"password|code|token|secret|authorization|email|phone|report|prompt|image.?url|"
    r"drug|symptom|content|body|query|string",
    re.IGNORECASE,
)
_SAFE_FIELDS = {
    "event",
    "level",
    "service",
    "request_id",
    "task_id",
    "route",
    "status_code",
    "duration_ms",
    "code",
    "error_code",
}
_SAFE_EVENT = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_SAFE_ROUTE = re.compile(r"^/[a-zA-Z0-9_./{}-]{1,200}$")
_OPAQUE_ROUTE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{32,}$")
_UUID_ROUTE_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def redact_sensitive_fields(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in event_dict.items():
        name = str(key)
        if name not in _SAFE_FIELDS:
            continue
        if _SENSITIVE_KEYS.search(name):
            safe[name] = "[REDACTED]"
        elif name == "event":
            safe[name] = (
                value
                if isinstance(value, str) and _SAFE_EVENT.fullmatch(value)
                else "application_event"
            )
        elif name == "route":
            safe[name] = (
                value
                if isinstance(value, str)
                and _SAFE_ROUTE.fullmatch(value)
                and not any(
                    _OPAQUE_ROUTE_SEGMENT.fullmatch(part) or _UUID_ROUTE_SEGMENT.fullmatch(part)
                    for part in value.split("/")
                )
                else "[REDACTED]"
            )
        elif name in {"service", "code", "error_code", "level"}:
            safe[name] = (
                value if isinstance(value, str) and _SAFE_EVENT.fullmatch(value) else "[REDACTED]"
            )
        elif name in {"status_code", "duration_ms"}:
            safe[name] = value if isinstance(value, (int, float)) else "[REDACTED]"
        else:
            # Correlation identifiers are retained only in canonical UUID form.
            safe[name] = (
                value
                if isinstance(value, str)
                and re.fullmatch(
                    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                    value,
                )
                else "[REDACTED]"
            )
    return safe


def configure_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level, logging.INFO)
    # Opaque upload/download capabilities are path segments. Uvicorn's default
    # access formatter logs the raw URL, so application access logs are the only
    # HTTP log source and use RequestIdMiddleware's route template instead.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = True
    access_logger.propagate = False
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_sensitive_fields,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
