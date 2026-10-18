"""F09 strict Agent schema and OpenAPI contract tests (T73)."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError
from starlette.requests import Request

from gutcare.analysis.advice import (
    AdviceCallbackBody,
    AdvicePageRead,
    AdviceRead,
    AdviceService,
    RiskPriorityContext,
    _is_safe_knowledge_citation,
    _service,
    _snapshot_has_explicit_diagnosis,
)
from gutcare.app import create_app
from gutcare.config import Settings
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


def test_advice_accepts_snapshot_bound_mood_evidence_but_not_note_fields() -> None:
    payload = _payload()
    payload["advice"][0]["evidence"] = [
        {
            "evidence_type": "patient",
            "source_type": "mood_record",
            "source_id": "00000000-0000-4000-8000-000000000003",
            "source_version": 2,
            "locator": "mood_record:00000000-0000-4000-8000-000000000003",
        }
    ]
    AdviceCallbackBody.model_validate(payload)
    payload["advice"][0]["evidence"][0]["note"] = "must not be accepted"
    with pytest.raises(ValidationError):
        AdviceCallbackBody.model_validate(payload)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.org/path", True),
        ("https://user:password@example.org/path", False),
        ("http://example.org/path", False),
        ("javascript:alert(1)", False),
        ("file:///etc/passwd", False),
        ("https://", False),
        (None, True),
    ],
)
def test_knowledge_citation_requires_plain_https_host(url: str | None, expected: bool) -> None:
    assert _is_safe_knowledge_citation(url) is expected


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
    advice_schema = public["components"]["schemas"]["AdviceRead"]
    assert advice_schema["properties"]["status"]["enum"] == [
        "new",
        "read",
        "archived",
    ]
    assert "basis_updated" in advice_schema["properties"]
    assert "risk_priority_context" in advice_schema["required"]
    context_schema = public["components"]["schemas"]["RiskPriorityContext"]
    assert context_schema["properties"]["severity"]["enum"] == ["seek_care", "emergency"]
    assert context_schema["properties"]["status"]["enum"] == ["unread", "read", "reevaluated"]
    assert public["components"]["schemas"]["AdvicePageRead"]["properties"]["next_cursor"][
        "type"
    ] == [
        "string",
        "null",
    ]
    list_params = public["paths"]["/advice"]["get"]["parameters"]
    assert {param["name"] for param in list_params} == {"limit", "cursor"}


def test_advice_runtime_and_yaml_have_matching_operations_statuses_and_schemas() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    runtime = create_app(Settings(env="test")).openapi()

    def without_yaml_nulls(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: without_yaml_nulls(item) for key, item in value.items() if item is not None
            }
        if isinstance(value, list):
            return [without_yaml_nulls(item) for item in value]
        return value

    operations = {
        ("/advice", "get"): (
            "listAdvice",
            {"200", "400", "401", "404", "422", "500", "503"},
            "AdvicePageRead",
        ),
        ("/advice/{advice_id}", "get"): (
            "getAdvice",
            {"200", "401", "404", "422", "500", "503"},
            "AdviceRead",
        ),
        ("/advice/{advice_id}/read", "post"): (
            "readAdvice",
            {"200", "401", "404", "422", "500", "503"},
            "AdviceRead",
        ),
        ("/advice/{advice_id}/archive", "post"): (
            "archiveAdvice",
            {"200", "401", "404", "422", "500", "503"},
            "AdviceRead",
        ),
        ("/advice/{advice_id}/feedback", "put"): (
            "updateAdviceFeedback",
            {"200", "401", "404", "409", "422", "500", "503"},
            "AdviceFeedbackRead",
        ),
    }
    for (path, method), (operation_id, statuses, response_schema) in operations.items():
        yaml_operation = contract["paths"][path][method]
        runtime_operation = runtime["paths"][f"/api/v1{path}"][method]
        assert yaml_operation["operationId"] == runtime_operation["operationId"] == operation_id
        assert set(yaml_operation["responses"]) == set(runtime_operation["responses"]) == statuses
        expected = f"#/components/schemas/{response_schema}"
        assert (
            yaml_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == expected
        )
        assert (
            runtime_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == expected
        )
        yaml_success = yaml_operation["responses"]["200"]["content"]["application/json"]["example"]
        runtime_success = runtime_operation["responses"]["200"]["content"]["application/json"][
            "examples"
        ]["example"]["value"]
        assert runtime_success == without_yaml_nulls(yaml_success)
        advice_example = (
            yaml_success["items"][0] if response_schema == "AdvicePageRead" else yaml_success
        )
        expected_advice_status = {
            "getAdvice": "new",
            "readAdvice": "read",
            "archiveAdvice": "archived",
        }
        if operation_id in expected_advice_status:
            assert advice_example["status"] == expected_advice_status[operation_id]
        if operation_id in {"listAdvice", "getAdvice", "readAdvice", "archiveAdvice"}:
            assert advice_example["body"] == "可继续记录相关情况供后续回顾"

        yaml_unavailable = yaml_operation["responses"]["503"]["content"][
            "application/problem+json"
        ]["example"]
        runtime_unavailable = runtime_operation["responses"]["503"]["content"][
            "application/problem+json"
        ]["examples"]["problem"]["value"]
        assert runtime_unavailable == yaml_unavailable

    assert AdvicePageRead.model_validate({"items": [], "next_cursor": None})
    assert AdviceRead.model_fields["risk_priority_context"].is_required()
    context = RiskPriorityContext(
        alert_id="00000000-0000-4000-8000-000000000004",
        severity="emergency",
        status="reevaluated",
        triggered_at="2026-10-01T00:00:00Z",
    )
    assert context.status == "reevaluated"


def test_missing_advice_service_is_reported_as_503_not_500() -> None:
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(advice_service=None)),
        }
    )
    with pytest.raises(Problem) as err:
        _service(request)
    assert err.value.status == 503
    assert err.value.code == "SERVICE_UNAVAILABLE"


def test_advice_cursor_is_stable_and_rejects_malformed_values_as_problem() -> None:
    instant = datetime(2026, 10, 16, 8, 12, 5, 123456, tzinfo=UTC)
    advice_id = uuid4()
    cursor = AdviceService._encode_cursor(instant, advice_id)
    assert AdviceService._decode_cursor(cursor) == (instant, advice_id)
    for invalid in ("?", "!!!!", "e30", "bm90LWRhdGV8bm90LXV1aWQ"):
        with pytest.raises(Problem) as err:
            AdviceService._decode_cursor(invalid)
        assert err.value.status == 400 and err.value.code == "INVALID_CURSOR"
