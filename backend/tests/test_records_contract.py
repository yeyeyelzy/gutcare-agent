"""F03-F05 payload contracts are strict and reject unconfirmed/model metadata."""

import pytest
import yaml
from pydantic import ValidationError

from gutcare.records.api import RecordWrite, validate_payload
from gutcare.records.service import build_risk_facts, evaluate_condition
from gutcare.shared.errors import Problem


def test_diet_record_allows_manual_no_image_and_rejects_extra_fields() -> None:
    value = RecordWrite.model_validate(
        {
            "occurred_at": "2026-10-14T08:00:00+08:00",
            "payload": {"text_description": "米饭、蔬菜"},
        }
    )
    payload = validate_payload("diet-records", value.payload.model_dump(exclude_unset=True))
    assert payload == {"text_description": "米饭、蔬菜"}

    with pytest.raises(ValidationError):
        RecordWrite.model_validate(
            {
                "occurred_at": "2026-10-14T08:00:00+08:00",
                "payload": {"text_description": "manual", "source_type": "ai_candidate"},
            }
        )


def test_stool_record_checks_bristol_range() -> None:
    with pytest.raises(ValidationError):
        RecordWrite.model_validate(
            {"occurred_at": "2026-10-14T08:00:00Z", "payload": {"bristol_type": 8}}
        )


def test_symptom_record_keeps_multiple_confirmed_items() -> None:
    value = RecordWrite.model_validate(
        {
            "occurred_at": "2026-10-14T08:00:00Z",
            "payload": {
                "items": [
                    {"symptom_code": "abdominal_pain", "severity": 4},
                    {"symptom_code": "bloating", "severity": 2},
                ]
            },
        }
    )
    payload = validate_payload("symptom-records", value.payload.model_dump(exclude_unset=True))
    assert len(payload["items"]) == 2

    with pytest.raises(Problem) as error:
        validate_payload(
            "symptom-records",
            {"items": [{"symptom_code": "abdominal_pain", "patient_confirmed": False}]},
        )
    assert error.value.status == 422


def test_payload_type_must_match_record_type_path() -> None:
    value = RecordWrite.model_validate(
        {"occurred_at": "2026-10-14T08:00:00Z", "payload": {"bristol_type": 3}}
    )
    with pytest.raises(Problem) as error:
        validate_payload("diet-records", value.payload.model_dump(exclude_unset=True))
    assert error.value.status == 422


def test_fastapi_openapi_exposes_record_payload_union_and_risk_routes() -> None:
    from gutcare.app import create_app
    from gutcare.config import Settings

    schema = create_app(settings=Settings(env="test")).openapi()
    operation = schema["paths"]["/api/v1/{record_type}"]["post"]
    record_schema = schema["components"]["schemas"]["RecordWrite"]
    payload_schema = record_schema["properties"]["payload"]
    assert operation["parameters"][0]["schema"]["enum"] == [
        "diet-records",
        "stool-records",
        "symptom-records",
    ]
    assert "anyOf" in payload_schema
    assert "/api/v1/risk-alerts/{alert_id}/read" in schema["paths"]
    assert "/api/v1/risk-alerts/{alert_id}/reevaluate" in schema["paths"]
    operations = [
        ("/api/v1/{record_type}", "get"),
        ("/api/v1/{record_type}", "post"),
        ("/api/v1/{record_type}/{record_id}", "get"),
        ("/api/v1/{record_type}/{record_id}", "patch"),
        ("/api/v1/{record_type}/{record_id}", "delete"),
        ("/api/v1/symptom-records/{record_id}/status-history", "get"),
        ("/api/v1/risk-alerts", "get"),
        ("/api/v1/risk-alerts/{alert_id}", "get"),
        ("/api/v1/risk-alerts/{alert_id}/read", "post"),
        ("/api/v1/risk-alerts/{alert_id}/reevaluate", "post"),
    ]
    for path, method in operations:
        assert "401" in schema["paths"][path][method]["responses"]
    history_response = schema["paths"]["/api/v1/symptom-records/{record_id}/status-history"]["get"][
        "responses"
    ]["200"]
    assert history_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SymptomStatusHistory"
    }
    history_schema = schema["components"]["schemas"]["SymptomStatusHistory"]
    assert history_schema["required"] == ["symptom_record_id", "current_status", "events"]
    assert history_schema["properties"]["current_status"]["enum"] == ["ongoing", "relieved"]
    delete_operation = schema["paths"]["/api/v1/{record_type}/{record_id}"]["delete"]
    delete_version = next(
        parameter
        for parameter in delete_operation["parameters"]
        if parameter["name"] == "record_version"
    )
    assert delete_version["in"] == "query" and delete_version["required"] is True
    assert delete_version["schema"]["minimum"] == 1


def test_symptom_codes_are_controlled_and_other_needs_description() -> None:
    base = {"occurred_at": "2026-10-14T08:00:00Z"}
    assert (
        validate_payload(
            "symptom-records",
            {"items": [{"symptom_code": "other", "other_description": "食欲异常"}]},
        )["items"][0]["other_description"]
        == "食欲异常"
    )
    for item in (
        {"symptom_code": "arbitrary_free_text"},
        {"symptom_code": "other"},
        {"symptom_code": "bloating", "other_description": "无效"},
    ):
        with pytest.raises(Problem):
            validate_payload("symptom-records", {"items": [item]})
    with pytest.raises(ValidationError):
        RecordWrite.model_validate({**base, "payload": {"items": [{"symptom_code": "free text"}]}})


def test_symptom_status_is_strict_and_defaults_to_ongoing() -> None:
    value = RecordWrite.model_validate(
        {
            "occurred_at": "2026-10-14T08:00:00Z",
            "payload": {"items": [{"symptom_code": "bloating"}]},
        }
    )
    assert value.payload.symptom_status == "ongoing"
    with pytest.raises(ValidationError):
        RecordWrite.model_validate(
            {
                "occurred_at": "2026-10-14T08:00:00Z",
                "payload": {"items": [{"symptom_code": "bloating"}], "symptom_status": "cured"},
            }
        )


def test_rule_dsl_supports_nested_not_and_rejects_malformed_shapes() -> None:
    facts = {"blood_reported": False, "urgency_level": 2}
    condition = {
        "all": [
            {"not": {"field": "blood_reported", "op": "eq", "value": True}},
            {"any": [{"field": "urgency_level", "op": "gte", "value": 2}]},
        ]
    }
    assert evaluate_condition(condition, facts) is True
    assert (
        evaluate_condition({"not": {"field": "blood_reported", "op": "eq", "value": True}}, facts)
        is True
    )
    assert (
        evaluate_condition(
            {"field": "symptom_codes", "op": "in", "value": ["abdominal_pain"]},
            {"symptom_codes": ["bloating", "abdominal_pain"]},
        )
        is True
    )
    for malformed in (
        {"not": [{"field": "blood_reported", "op": "eq", "value": True}]},
        {"not": {"field": "unknown", "op": "eq", "value": True}},
        {"field": "blood_reported", "op": "in", "value": True},
        {"all": [], "any": []},
        {"field": "blood_reported", "op": "eq"},
    ):
        with pytest.raises(ValueError):
            evaluate_condition(malformed, facts)


def test_risk_facts_exclude_all_free_text_and_preserve_typed_signals() -> None:
    facts = build_risk_facts(
        "stool-records",
        {
            "notes": "synthetic dangerous phrase",
            "color_code": "synthetic code",
            "process_sensation": ["synthetic phrase"],
            "blood_reported": True,
            "bristol_type": 7,
            "image_object_id": "not-a-rule-fact",
        },
    )
    assert facts == {"record_type": "stool-records", "bristol_type": 7, "blood_reported": True}
    assert evaluate_condition({"field": "blood_reported", "op": "eq", "value": True}, facts) is True
    assert "notes" not in facts and "color_code" not in facts
    with pytest.raises(ValueError):
        evaluate_condition(
            {"field": "notes", "op": "eq", "value": "synthetic dangerous phrase"}, facts
        )

    symptom_facts = build_risk_facts(
        "symptom-records",
        {
            "items": [
                {
                    "symptom_code": "other",
                    "other_description": "free text trigger phrase",
                    "severity": 8,
                    "body_location": "free text location",
                }
            ],
            "notes": "free text trigger phrase",
        },
    )
    assert symptom_facts["symptom_codes"] == ["other"]
    assert symptom_facts["symptom_severities"] == [8]
    assert "other_description" not in symptom_facts and "notes" not in symptom_facts


def test_record_and_risk_openapi_operations_declare_rfc9457_401() -> None:
    from pathlib import Path

    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "contracts/openapi/gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = contract["paths"]
    for path, method in (
        ("/{record_type}", "get"),
        ("/{record_type}", "post"),
        ("/{record_type}/{record_id}", "get"),
        ("/{record_type}/{record_id}", "patch"),
        ("/{record_type}/{record_id}", "delete"),
        ("/symptom-records/{record_id}/status-history", "get"),
        ("/risk-alerts", "get"),
        ("/risk-alerts/{alert_id}", "get"),
        ("/risk-alerts/{alert_id}/read", "post"),
        ("/risk-alerts/{alert_id}/reevaluate", "post"),
    ):
        response = paths[path][method]["responses"]["401"]
        assert response["$ref"] == "#/components/responses/Problem"
    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "contracts/openapi/gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    history_media = contract["paths"]["/symptom-records/{record_id}/status-history"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]
    assert history_media["schema"]["$ref"] == "#/components/schemas/SymptomStatusHistory"
    assert history_media["example"]["current_status"] == "relieved"
    assert history_media["example"]["events"][-1] == {
        "status": "relieved",
        "record_version": 2,
        "changed_at": "2026-10-14T02:15:00Z",
    }


def test_delete_record_version_conflict_is_rfc9457_problem() -> None:
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from gutcare.app import create_app
    from gutcare.auth.api import current_auth_context
    from gutcare.auth.service import AuthContext
    from gutcare.config import Settings
    from gutcare.records.api import get_record_service

    class ConflictService:
        def delete(self, _context, _record_type, _record_id, version):
            assert version == 3
            raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")

    app = create_app(settings=Settings(env="test"))
    app.dependency_overrides[current_auth_context] = lambda: AuthContext(
        user_id=uuid4(), session_id=uuid4()
    )
    app.dependency_overrides[get_record_service] = lambda: ConflictService()
    with TestClient(app) as client:
        response = client.delete(
            "/api/v1/diet-records/019a0000-0000-7000-8000-000000000031?record_version=3",
            headers={"Authorization": "Bearer fixture-access-token"},
        )
        assert response.status_code == 409
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "RECORD_VERSION_CONFLICT"
        assert response.json()["request_id"]
        missing = client.delete(
            "/api/v1/diet-records/019a0000-0000-7000-8000-000000000031",
            headers={"Authorization": "Bearer fixture-access-token"},
        )
        assert missing.status_code == 422
        assert missing.headers["content-type"].startswith("application/problem+json")
