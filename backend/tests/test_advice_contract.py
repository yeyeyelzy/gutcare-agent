"""F09 strict Agent schema and OpenAPI contract tests (T73)."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError

from gutcare.analysis.advice import (
    AdviceCallbackBody,
    AdviceService,
    _snapshot_has_explicit_diagnosis,
)
from gutcare.shared.errors import Problem


def _payload() -> dict[str, object]:
    return {
        "callback_id": "00000000-0000-4000-8000-000000000001",
        "schema_version": "1.0",
        "advice": [
            {
                "category": "diet",
                "priority": "routine",
                "title": "Continue keeping a meal record",
                "body": "Record meals and symptoms for later review.",
                "uncertainty": {"level": "moderate", "reasons": ["Few records"]},
                "applicability": {"scope": "general", "limitations": []},
                "safety_boundary": {
                    "not_diagnosis": True,
                    "not_prescription": True,
                    "risk_alert_priority": True,
                },
                "version": "1.0",
                "evidence": [
                    {
                        "evidence_type": "patient",
                        "source_type": "diet_record",
                        "source_id": "00000000-0000-4000-8000-000000000002",
                        "source_version": 3,
                        "locator": "diet_record:00000000-0000-4000-8000-000000000002",
                    }
                ],
            }
        ],
    }


def test_advice_callback_requires_explicit_structured_safety_and_evidence() -> None:
    AdviceCallbackBody.model_validate(_payload())
    for change in (
        {"raw_model_output": "forbidden"},
        {"advice": [{**_payload()["advice"][0], "category": "diagnosis"}]},
        {
            "advice": [
                {
                    **_payload()["advice"][0],
                    "safety_boundary": {"not_diagnosis": False},
                }
            ]
        },
        {
            "advice": [
                {
                    **_payload()["advice"][0],
                    "evidence": [
                        {
                            "evidence_type": "knowledge",
                            "knowledge_ref": "kb:guide",
                            "knowledge_version": "v2",
                            "knowledge_title": "Guide",
                            "knowledge_publisher": "Publisher",
                            "body": "must not accept knowledge text",
                        }
                    ],
                }
            ]
        },
    ):
        candidate = {**_payload(), **change}
        with pytest.raises(ValidationError):
            AdviceCallbackBody.model_validate(candidate)


@pytest.mark.parametrize("certainty", ["suspected", "rule_out", "history", None])
def test_disease_specific_advice_gate_requires_explicit_diagnosis_in_snapshot(
    certainty: str | None,
) -> None:
    records = [
        {
            "record_type": "confirmed_medical_fact",
            "confirmation_status": "confirmed",
            "payload": {
                "field_code": "diagnosis",
                "value": {"text": "synthetic diagnosis", "certainty": certainty},
            },
        }
    ]
    assert _snapshot_has_explicit_diagnosis(records) is False
    records[0]["payload"]["value"]["certainty"] = "explicit"  # type: ignore[index]
    assert _snapshot_has_explicit_diagnosis(records) is True


def test_disease_specific_gate_ignores_current_patient_state_and_requires_snapshot_record() -> None:
    assert _snapshot_has_explicit_diagnosis([]) is False


def test_advice_contracts_match_callback_and_patient_lifecycle_schemas() -> None:
    root = Path(__file__).resolve().parents[2]
    agent = yaml.safe_load((root / "contracts/agent/agent-v1.yaml").read_text(encoding="utf-8"))
    public = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    assert "/agent/advice/{task_id}/callback" in agent["paths"]
    callback_409 = agent["paths"]["/agent/advice/{task_id}/callback"]["post"]["responses"]["409"]
    assert "不得自动重试" in callback_409["description"]
    rejection_example = callback_409["content"]["application/problem+json"]["examples"][
        "adviceNotApplicable"
    ]["value"]
    assert rejection_example["code"] == "ADVICE_NOT_APPLICABLE"
    assert "do not retry" in rejection_example["detail"]
    assert (
        agent["paths"]["/agent/advice/{task_id}/callback"]["post"]["operationId"]
        == "submitAdviceCallback"
    )
    assert set(public["paths"]) >= {
        "/advice",
        "/advice/{advice_id}",
        "/advice/{advice_id}/read",
        "/advice/{advice_id}/archive",
        "/advice/{advice_id}/feedback",
    }
    assert public["components"]["schemas"]["Advice"]["properties"]["status"]["enum"] == [
        "new",
        "read",
        "archived",
    ]
    assert "basis_updated" in public["components"]["schemas"]["Advice"]["properties"]
    assert public["components"]["schemas"]["AdvicePage"]["properties"]["next_cursor"]["type"] == [
        "string",
        "null",
    ]
    list_params = public["paths"]["/advice"]["get"]["parameters"]
    assert {param["name"] for param in list_params} == {"limit", "cursor"}


def test_advice_cursor_is_stable_and_rejects_malformed_values_as_problem() -> None:
    instant = datetime(2026, 10, 16, 8, 12, 5, 123456, tzinfo=UTC)
    advice_id = uuid4()
    cursor = AdviceService._encode_cursor(instant, advice_id)
    assert AdviceService._decode_cursor(cursor) == (instant, advice_id)
    for invalid in ("?", "!!!!", "e30", "bm90LWRhdGV8bm90LXV1aWQ"):
        with pytest.raises(Problem) as err:
            AdviceService._decode_cursor(invalid)
        assert err.value.status == 400 and err.value.code == "INVALID_CURSOR"
