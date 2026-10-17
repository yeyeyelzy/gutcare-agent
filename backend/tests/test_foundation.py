"""Tests for the backend application foundation."""

from uuid import UUID  # noqa: I001 - gutcare.app preloads logging before FastAPI on Python 3.13

import pytest
from pydantic import ValidationError

from gutcare.app import DatabaseReadiness, create_app
from gutcare.config import Settings
from gutcare.shared.logging import redact_sensitive_fields

from fastapi import APIRouter
from fastapi.testclient import TestClient


def settings(database_url: str | None = None) -> Settings:
    return Settings(env="test", database_url=database_url)


def test_liveness_and_request_id() -> None:
    client = TestClient(create_app(settings()))
    response = client.get(
        "/health/live", headers={"X-Request-ID": "8e21a42e-24da-4e57-96d4-e2fcad056e64"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Request-ID"] == "8e21a42e-24da-4e57-96d4-e2fcad056e64"


def test_invalid_request_id_is_replaced() -> None:
    response = TestClient(create_app(settings())).get(
        "/health/live", headers={"X-Request-ID": "bad"}
    )
    UUID(response.headers["X-Request-ID"])


def test_readiness_fails_without_configured_database_or_probe() -> None:
    response = TestClient(create_app(settings())).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_uses_injected_database_probe() -> None:
    app = create_app(
        settings("postgresql+psycopg://user:pass@localhost/gutcare_business"),
        database_probe=lambda: DatabaseReadiness(available=True, schema_current=True),
    )
    assert TestClient(app).get("/health/ready").json() == {"status": "ready"}


def test_readiness_fails_when_database_probe_is_unavailable() -> None:
    app = create_app(
        settings("postgresql+psycopg://user:pass@localhost/gutcare_business"),
        database_probe=lambda: DatabaseReadiness(available=False, schema_current=False),
    )
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_when_database_schema_is_outdated() -> None:
    app = create_app(
        settings("postgresql+psycopg://user:pass@localhost/gutcare_business"),
        database_probe=lambda: DatabaseReadiness(available=True, schema_current=False),
    )
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503


def test_readiness_fails_when_privacy_replay_is_not_clear() -> None:
    app = create_app(
        settings("postgresql+psycopg://user:pass@localhost/gutcare_business"),
        database_probe=lambda: DatabaseReadiness(
            available=True, schema_current=True, privacy_replay_clear=False
        ),
    )
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_fails_closed_when_database_probe_raises() -> None:
    def unavailable() -> DatabaseReadiness:
        raise RuntimeError("connection details must not be exposed")

    app = create_app(
        settings("postgresql+psycopg://user:pass@localhost/gutcare_business"),
        database_probe=unavailable,
    )
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_application_registers_supplied_module_routers() -> None:
    router = APIRouter(prefix="/example")

    @router.get("/resource")
    def get_resource() -> dict[str, str]:
        return {"result": "ok"}

    response = TestClient(create_app(settings(), routers=[router])).get("/example/resource")
    assert response.status_code == 200
    assert response.json() == {"result": "ok"}


def test_problem_response_matches_contract_and_carries_request_id() -> None:
    response = TestClient(create_app(settings())).get("/missing")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "HTTP_404"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_uvicorn_raw_access_logging_is_disabled_for_path_capabilities() -> None:
    import logging

    from gutcare.shared.logging import configure_logging

    configure_logging("INFO")
    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.disabled is True
    assert access_logger.propagate is False


def test_redaction_filters_sensitive_fields() -> None:
    event = {
        "event": "request",
        "password": "secret",
        "email": "a@example.invalid",
        "route": "/health/ready",
        "request_id": "8e21a42e-24da-4e57-96d4-e2fcad056e64",
        "unreviewed_field": "sensitive value",
    }
    result = redact_sensitive_fields(None, "info", event)
    assert "password" not in result
    assert "email" not in result
    assert result["route"] == "/health/ready"
    assert result["request_id"] == event["request_id"]
    assert "unreviewed_field" not in result


def test_redaction_replaces_unstructured_event_text() -> None:
    result = redact_sensitive_fields(
        None, "info", {"event": "login failed for user a@example.invalid"}
    )
    assert result["event"] == "application_event"


def test_production_requires_approved_registration_notice_configuration() -> None:
    with pytest.raises(ValidationError, match="registration notice configuration is incomplete"):
        Settings(env="production")

    complete = {
        "privacy_policy_summary_hash": "a" * 64,
        "health_data_processing_summary_hash": "b" * 64,
        "privacy_policy_version": "privacy-2026-10",
        "health_data_processing_policy_version": "health-2026-10",
    }
    assert Settings(env="production", **complete).privacy_policy_version == "privacy-2026-10"


@pytest.mark.parametrize(
    "field,value",
    [
        ("privacy_policy_version", "test-only-privacy-v1"),
        ("health_data_processing_policy_version", "dev-health-v1"),
        ("health_data_processing_policy_version", "development_health-v1"),
        ("privacy_policy_summary_hash", "not-a-sha256"),
    ],
)
def test_production_rejects_test_notice_versions_and_invalid_hashes(field: str, value: str) -> None:
    complete = {
        "privacy_policy_summary_hash": "a" * 64,
        "health_data_processing_summary_hash": "b" * 64,
        "privacy_policy_version": "privacy-2026-10",
        "health_data_processing_policy_version": "health-2026-10",
    }
    complete[field] = value
    with pytest.raises(ValidationError):
        Settings(env="production", **complete)
