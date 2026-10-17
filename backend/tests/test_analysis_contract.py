"""Strict F08 Agent result boundary tests."""

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gutcare.analysis.api import AgentResult, ResultEvidence, TaskCreate, validate_analysis_range
from gutcare.app import create_app
from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.config import Settings


def _payload() -> dict[str, object]:
    return {
        "callback_id": "00000000-0000-4000-8000-000000000001",
        "status": "succeeded",
        "schema_version": "1.0",
        "summary": "summary",
        "observations": ["observation"],
        "evidence": [],
        "uncertainties": ["uncertainty"],
        "missing_data": ["missing"],
    }


def test_agent_result_enforces_each_item_length_and_strict_string_types() -> None:
    AgentResult.model_validate(_payload())
    for field, value in (
        ("observations", "x" * 501),
        ("uncertainties", "x" * 501),
        ("missing_data", "x" * 121),
        ("observations", 42),
        ("uncertainties", 42),
        ("missing_data", 42),
    ):
        candidate = _payload()
        candidate[field] = [value]
        with pytest.raises(ValidationError):
            AgentResult.model_validate(candidate)


def test_analysis_range_semantics_have_no_implicit_default_boundaries() -> None:
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    assert validate_analysis_range("comprehensive_health_analysis", None, None) == (None, None)
    assert validate_analysis_range("comprehensive_health_analysis", start, end) == (start, end)
    assert validate_analysis_range("periodic_summary", start, end) == (start, end)
    plus_two = datetime.fromisoformat("2026-01-01T02:00:00+02:00")
    plus_two_end = plus_two + timedelta(hours=1)
    assert validate_analysis_range("comprehensive_health_analysis", plus_two, plus_two_end) == (
        start,
        start + timedelta(hours=1),
    )
    normalized = TaskCreate.model_validate(
        {
            "analysis_type": "comprehensive_health_analysis",
            "requested_from": plus_two,
            "requested_to": plus_two_end,
        }
    )
    assert normalized.requested_from == start
    assert normalized.requested_to == start + timedelta(hours=1)
    for kind in ("comprehensive_health_analysis", "periodic_summary"):
        with pytest.raises(ValueError):
            validate_analysis_range(kind, start, None)
        with pytest.raises(ValueError):
            validate_analysis_range(kind, None, end)
    with pytest.raises(ValueError):
        validate_analysis_range("periodic_summary", None, None)
    with pytest.raises(ValidationError):
        TaskCreate.model_validate(
            {"analysis_type": "comprehensive_health_analysis", "requested_from": start}
        )


def test_agent_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentResult.model_validate({**_payload(), "raw_model_output": "must not persist"})


def test_agent_result_evidence_version_and_uuid_types_are_strict() -> None:
    base = {
        "source_type": "diet_record",
        "source_id": "00000000-0000-4000-8000-000000000002",
        "source_version": 2,
        "locator": "diet_record:source",
    }
    ResultEvidence.model_validate(base)
    for value in ("2", True, 2.0):
        with pytest.raises(ValidationError):
            ResultEvidence.model_validate({**base, "source_version": value})
    for field, value in (("source_id", 2), ("source_id", True)):
        with pytest.raises(ValidationError):
            ResultEvidence.model_validate({**base, field: value})
    for value in (2, True):
        with pytest.raises(ValidationError):
            AgentResult.model_validate({**_payload(), "callback_id": value})


def test_f08_contracts_match_strict_result_item_limits_and_deleted_source_projection() -> None:
    root = Path(__file__).resolve().parents[2]
    agent = yaml.safe_load((root / "contracts/agent/agent-v1.yaml").read_text(encoding="utf-8"))
    public = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    agent_result = agent["components"]["schemas"]["AgentResult"]["properties"]
    public_result = public["components"]["schemas"]["AnalysisResult"]["properties"]
    for schema in (agent_result, public_result):
        assert schema["observations"]["items"]["maxLength"] == 500
        assert schema["uncertainties"]["items"]["maxLength"] == 500
        assert schema["missing_data"]["items"]["maxLength"] == 120
    evidence = public_result["evidence"]["items"]
    if "$ref" in evidence:
        evidence = public["components"]["schemas"][evidence["$ref"].split("/")[-1]]
    assert evidence["properties"]["source_version"]["type"] == "integer"
    assert evidence["properties"]["source_version"]["minimum"] == 1
    assert "source_deleted" in evidence["required"]
    assert evidence["properties"]["source_deleted"]["type"] == "boolean"
    assert evidence["properties"]["locator"]["type"] == ["string", "null"]


def test_h2_agent_inputs_carry_separate_mood_records_and_creation_consent_snapshot() -> None:
    root = Path(__file__).resolve().parents[2]
    agent = yaml.safe_load((root / "contracts/agent/agent-v1.yaml").read_text(encoding="utf-8"))
    schemas = agent["components"]["schemas"]
    task_inputs = schemas["TaskInputs"]
    assert {"mood_records", "consent_scope_snapshot"} <= set(task_inputs["required"])
    consent_snapshot = task_inputs["properties"]["consent_scope_snapshot"]
    assert set(consent_snapshot["required"]) == {
        "health_data_processing",
        "mood_data_processing",
        "mood_ai_sharing",
        "third_party_ai",
    }
    mood_record = task_inputs["properties"]["mood_records"]["items"]["allOf"][1]
    assert mood_record["properties"]["record_type"]["const"] == "mood_record"
    mood_payload = schemas["MoodSnapshotPayload"]
    assert set(mood_payload["properties"]) == {"occurred_at", "mood_level", "emotion_tags"}
    assert "note" not in mood_payload["properties"]
    ResultEvidence.model_validate(
        {
            "source_type": "mood_record",
            "source_id": "00000000-0000-4000-8000-000000000003",
            "source_version": 1,
            "locator": "mood_record:source",
        }
    )


def test_analysis_range_openapi_describes_shared_explicit_semantics() -> None:
    root = Path(__file__).resolve().parents[2]
    public = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    preview = public["paths"]["/analysis-tasks/preview"]["get"]
    create = public["paths"]["/analysis-tasks"]["post"]
    assert "不存在隐含默认边界" in preview["description"]
    assert "periodic_summary" in create["description"]
    assert "requested_from" in create["description"]


def test_preview_and_create_single_sided_ranges_are_rfc9457_422() -> None:
    app = create_app(Settings(env="test"))
    app.state.analysis_service = object()
    app.dependency_overrides[current_auth_context] = lambda: AuthContext(
        user_id=uuid4(), session_id=uuid4()
    )
    timestamp = "2026-01-01T00:00:00Z"
    with TestClient(app) as client:
        for supplied_field in ("requested_from", "requested_to"):
            preview = client.get(
                "/api/v1/analysis-tasks/preview",
                params={"analysis_type": "periodic_summary", supplied_field: timestamp},
            )
            assert preview.status_code == 422
            assert preview.headers["content-type"].startswith("application/problem+json")
            assert preview.json()["code"] == "VALIDATION_ERROR"

            create_body = {"analysis_type": "periodic_summary", supplied_field: timestamp}
            created = client.post(
                "/api/v1/analysis-tasks",
                headers={"Idempotency-Key": "single-range-contract-001"},
                json=create_body,
            )
            assert created.status_code == 422
            assert created.headers["content-type"].startswith("application/problem+json")
            assert created.json()["code"] == "VALIDATION_ERROR"
