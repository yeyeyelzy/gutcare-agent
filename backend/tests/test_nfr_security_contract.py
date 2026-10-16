"""Cross-cutting NFR-02/NFR-04 checks against the frozen API contract."""

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from gutcare.app import create_app
from gutcare.auth.api import get_auth_service
from gutcare.config import Settings
from gutcare.shared.logging import redact_sensitive_fields

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPOSITORY_ROOT / "contracts" / "openapi" / "gutcare-v1.yaml"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head"})
PROBLEM_REQUIRED = frozenset({"type", "title", "status", "code", "request_id"})
FORBIDDEN_ERROR_EXAMPLE_KEYS = re.compile(
    r"password|token|secret|email|phone|patient_id|object_key|bucket_name|prompt|source_locator",
    re.IGNORECASE,
)


def _contract() -> dict[str, Any]:
    parsed = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _resolve_response(contract: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    reference = response.get("$ref")
    if not reference:
        return response
    assert reference.startswith("#/components/responses/")
    name = reference.rsplit("/", 1)[-1]
    resolved = contract["components"]["responses"][name]
    return _resolve_response(contract, resolved)


def _normalized_contract_routes(contract: dict[str, Any]) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for path, path_item in contract["paths"].items():
        for method in path_item:
            if method.lower() in HTTP_METHODS:
                routes.add((str(path), method.lower()))
    return routes


def _normalized_runtime_routes(document: dict[str, Any]) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for raw_path, path_item in document["paths"].items():
        if raw_path.startswith("/internal/") or raw_path.startswith("/health/"):
            continue
        path = raw_path.removeprefix("/api/v1")
        if not path.startswith("/"):
            path = f"/{path}"
        for method in path_item:
            if method.lower() in HTTP_METHODS:
                routes.add((path, method.lower()))
    return routes


def test_runtime_business_routes_match_contract_paths_and_methods() -> None:
    contract = _contract()
    runtime = create_app(Settings(env="test")).openapi()
    contract_routes = _normalized_contract_routes(contract)
    runtime_routes = _normalized_runtime_routes(runtime)
    missing_contract = sorted(runtime_routes - contract_routes)
    missing_runtime = sorted(contract_routes - runtime_routes)
    assert not missing_contract and not missing_runtime, (
        f"runtime-only routes={missing_contract}; contract-only routes={missing_runtime}"
    )


def test_contract_errors_are_rfc9457_and_permission_paths_have_401() -> None:
    contract = _contract()
    components = contract["components"]["schemas"]
    assert PROBLEM_REQUIRED <= set(components["Problem"]["required"])
    missing_401: list[str] = []
    for path, path_item in contract["paths"].items():
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            operation_security = operation.get("security", contract.get("security", []))
            if operation_security:
                if "401" not in operation["responses"]:
                    missing_401.append(f"{method} {path}")
            for status, response_value in operation["responses"].items():
                if not str(status).startswith(("4", "5")):
                    continue
                response = _resolve_response(contract, response_value)
                media = response.get("content", {}).get("application/problem+json")
                assert media is not None, f"non-Problem error response: {method} {path} {status}"
                assert media.get("schema", {}).get("$ref") == "#/components/schemas/Problem"
                examples = list(media.get("examples", {}).values())
                if "example" in media:
                    examples.append({"value": media["example"]})
                for example_entry in examples:
                    example = example_entry.get("value", example_entry)
                    assert isinstance(example, dict)
                    assert PROBLEM_REQUIRED <= set(example)
                    assert int(example["status"]) == int(status)
                    forbidden = [key for key in example if FORBIDDEN_ERROR_EXAMPLE_KEYS.search(key)]
                    assert not forbidden, f"sensitive error example keys: {forbidden}"
    assert not missing_401, f"secured operations missing 401 Problem: {missing_401}"


def test_runtime_auth_error_is_a_problem_details_permission_response() -> None:
    application = create_app(Settings(env="test"))
    application.dependency_overrides[get_auth_service] = lambda: object()
    with TestClient(application) as client:
        response = client.get("/api/v1/patients/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert PROBLEM_REQUIRED <= set(body)
    assert body["status"] == 401
    assert body["code"] == "AUTHENTICATION_REQUIRED"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_sensitive_log_and_capability_url_scan() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.disabled and not access_logger.propagate
    capability = "c" * 64
    redacted = redact_sensitive_fields(
        None,
        "info",
        {
            "event": "http_request",
            "route": f"/uploads/{capability}",
            "url": f"https://example.invalid/uploads/{capability}",
            "path": f"/uploads/{capability}",
            "query": "access_token=token-sentinel&patient_id=patient-sentinel",
            "headers": {
                "authorization": "Bearer token-sentinel",
                "x-export-capability": "capability-sentinel",
            },
            "capability": capability,
            "request_id": "019a0000-0000-7000-8000-000000000099",
        },
    )
    rendered = repr(redacted)
    assert capability not in rendered
    assert "token-sentinel" not in rendered
    assert "patient-sentinel" not in rendered
    assert "capability-sentinel" not in rendered
    assert "/uploads/" not in rendered
