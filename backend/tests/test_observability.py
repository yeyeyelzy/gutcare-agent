"""Operations metrics remain low-cardinality and outside the patient API contract."""

import re
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gutcare.app import DatabaseReadiness, create_app
from gutcare.config import Settings
from gutcare.shared.metrics import OperationsMetrics

METRICS_TOKEN = "t" * 40


def test_metrics_disabled_by_default_and_hidden_from_openapi() -> None:
    app = create_app(Settings(env="test"))
    client = TestClient(app)
    assert client.get("/ops/metrics").status_code == 404
    assert "/ops/metrics" not in app.openapi()["paths"]


def test_metrics_requires_header_token_and_does_not_emit_token(caplog) -> None:
    app = create_app(Settings(env="test", metrics_enabled=True, metrics_token=METRICS_TOKEN))
    client = TestClient(app)
    assert client.get("/ops/metrics").status_code == 404
    assert client.get("/ops/metrics", headers={"X-Ops-Metrics-Token": "wrong"}).status_code == 404
    response = client.get("/ops/metrics", headers={"X-Ops-Metrics-Token": METRICS_TOKEN})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "gutcare_http_requests_total" in response.text
    assert METRICS_TOKEN not in response.text
    assert METRICS_TOKEN not in caplog.text
    assert "X-Ops-Metrics-Token" not in caplog.text
    assert "/ops/metrics" not in app.openapi()["paths"]


def test_metrics_enabled_requires_configured_secret() -> None:
    try:
        Settings(env="test", metrics_enabled=True)
    except ValidationError as error:
        assert "OPS_METRICS_TOKEN" in str(error)
    else:
        raise AssertionError("metrics must fail closed without a scrape token")


def test_metrics_capture_route_template_and_status_family_only() -> None:
    metrics = OperationsMetrics()
    metrics.set_route_templates({"/patients/{patient_id}/records"})
    metrics.observe_request("GET", "/patients/{patient_id}/records", 404, 0.125)
    metrics.observe_request("GET", "/patients/secret-person/records", 200, 0.25)
    scrape = metrics.registry
    from prometheus_client import generate_latest

    body = generate_latest(scrape).decode()
    assert 'route="/patients/{patient_id}/records"' in body
    assert 'status_family="4xx"' in body
    assert "secret-person" not in body
    assert 'route="unmatched"' in body


def test_readiness_probe_results_are_observable_without_probe_details() -> None:
    app = create_app(
        Settings(
            env="test",
            database_url="postgresql+psycopg://user:pass@localhost/gutcare_business",
            metrics_enabled=True,
            metrics_token=METRICS_TOKEN,
        ),
        database_probe=lambda: DatabaseReadiness(
            available=False, schema_current=False, privacy_replay_clear=False
        ),
    )
    app.state.database_engine = None
    client = TestClient(app)
    assert client.get("/health/ready").status_code == 503
    scrape = client.get("/ops/metrics", headers={"X-Ops-Metrics-Token": METRICS_TOKEN}).text
    assert 'result="not_ready"' in scrape
    assert 'component="database"} 0.0' in scrape
    assert "gutcare_metrics_db_snapshot_success 0.0" in scrape
    assert 'gutcare_worker_backlog{queue="privacy_deletion",state="backlog"} NaN' in scrape


def test_alert_rules_have_valid_prometheus_rule_shape_and_safe_labels() -> None:
    path = Path(__file__).parents[2] / "infra" / "observability" / "alerts.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["groups"]
    names: set[str] = set()
    for group in document["groups"]:
        assert group["name"]
        assert group["rules"]
        for rule in group["rules"]:
            assert rule["alert"] not in names
            names.add(rule["alert"])
            assert rule["expr"].strip()
            assert re.fullmatch(r"\d+[smhd]", rule.get("for", ""))
            assert rule["labels"].get("severity") in {"warning", "critical"}
            assert rule["annotations"].get("summary")
            serialized = repr(rule).lower()
            assert all(token not in serialized for token in ("patient_id", "object_key", "token"))
    assert {
        "GutCareApiHigh5xx",
        "GutCarePrivacyDeletionOverdue",
        "GutCareWorkerDeadLetter",
    } <= names
    registered = {metric.name for metric in OperationsMetrics().registry.collect()}
    registered.update(f"{name}_total" for name in tuple(registered) if name.endswith("_requests"))
    expression_names = {
        metric
        for group in document["groups"]
        for rule in group["rules"]
        for metric in re.findall(r"\b[a-zA-Z_:][a-zA-Z0-9_:]*(?=\s*(?:\{|\[|==|>|/))", rule["expr"])
    }
    assert expression_names <= registered
