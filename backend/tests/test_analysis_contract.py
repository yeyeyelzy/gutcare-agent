"""Strict F08 Agent result boundary tests."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gutcare.analysis.api import AgentResult, ResultEvidence


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
    assert evidence["properties"]["source_version"]["type"] == "integer"
    assert evidence["properties"]["source_version"]["minimum"] == 1
    assert "source_deleted" in evidence["required"]
    assert evidence["properties"]["source_deleted"]["type"] == "boolean"
    assert evidence["properties"]["locator"]["type"] == ["string", "null"]
