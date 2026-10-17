"""F07 DTO and F11 cursor contract checks (T87/T88)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gutcare.activity.api import ActivityPatch, ActivityWrite
from gutcare.activity.service import ActivityService
from gutcare.config import Settings
from gutcare.main import create_app
from gutcare.shared.errors import Problem


def test_activity_write_enums_and_bounds() -> None:
    valid = ActivityWrite.model_validate(
        {
            "activity_type": "other",
            "description": "瑜伽",
            "intensity": "moderate",
            "subjective_feeling": "better",
            "duration_minutes": 1440,
            "occurred_at": "2026-10-16T08:00:00+08:00",
        }
    )
    assert valid.occurred_at.tzinfo is not None
    for update in (
        {
            "activity_type": "other",
            "intensity": "low",
            "subjective_feeling": "same",
            "duration_minutes": 30,
            "occurred_at": "2026-10-16T00:00:00Z",
        },
        {
            "activity_type": "walking",
            "description": "瑜伽",
            "intensity": "low",
            "subjective_feeling": "same",
            "duration_minutes": 30,
            "occurred_at": "2026-10-16T00:00:00Z",
        },
        {
            "activity_type": "walking",
            "intensity": "intense",
            "subjective_feeling": "same",
            "duration_minutes": 30,
            "occurred_at": "2026-10-16T00:00:00Z",
        },
        {
            "activity_type": "walking",
            "intensity": "low",
            "subjective_feeling": "same",
            "duration_minutes": 0,
            "occurred_at": "2026-10-16T00:00:00Z",
        },
        {
            "activity_type": "walking",
            "intensity": "low",
            "subjective_feeling": "same",
            "duration_minutes": 30,
            "occurred_at": "2026-10-16T00:00:00",
        },
        {
            "activity_type": "walking",
            "intensity": "low",
            "subjective_feeling": "same",
            "duration_minutes": 30,
            "occurred_at": "2026-10-16T00:00:00Z",
            "patient_id": "00000000-0000-0000-0000-000000000000",
        },
    ):
        with pytest.raises(ValidationError):
            ActivityWrite.model_validate(update)


def test_activity_patch_requires_optimistic_version_and_strict_fields() -> None:
    with pytest.raises(ValidationError):
        ActivityPatch.model_validate({"duration_minutes": 40})
    with pytest.raises(ValidationError):
        ActivityPatch.model_validate({"record_version": 1, "patient_id": "attacker"})
    for field in (
        "activity_type",
        "intensity",
        "subjective_feeling",
        "duration_minutes",
        "occurred_at",
    ):
        with pytest.raises(ValidationError):
            ActivityPatch.model_validate({"record_version": 1, field: None})
    assert (
        ActivityPatch.model_validate({"record_version": 1, "description": None}).description is None
    )


def test_history_cursor_is_signed_and_rejects_tampering() -> None:
    svc = ActivityService(None, "a" * 32)  # type: ignore[arg-type]
    encoded = svc._encode(
        {
            "occurred_at": datetime.now(UTC).isoformat(),
            "type": "activity",
            "id": "00000000-0000-0000-0000-000000000001",
            "filters": {"since": None, "until": None},
        }
    )
    assert svc._decode(encoded)["type"] == "activity"
    with pytest.raises(Problem) as mismatched:
        svc._check_filters(svc._decode(encoded), {"since": None, "until": None, "categories": None})
    assert mismatched.value.code == "INVALID_CURSOR"
    with pytest.raises(Exception, match="History cursor"):
        svc._decode(encoded[:-2] + "xx")


def test_activity_and_history_openapi_are_present_and_strict() -> None:
    schema = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "openapi" / "gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert "/activity-records" in schema["paths"]
    assert "/history/timeline" in schema["paths"]
    assert "/trends" in schema["paths"]
    assert schema["components"]["schemas"]["ActivityWrite"]["additionalProperties"] is False
    target_type = schema["components"]["schemas"]["HistoryPage"]["properties"]["items"]["items"][
        "properties"
    ]["target"]["properties"]["type"]["enum"]
    assert target_type == [
        "diet_record",
        "stool_record",
        "symptom_record",
        "mood_record",
        "medication_checkin",
        "activity_record",
        "advice",
    ]
    assert schema["paths"]["/history/timeline"]["get"]["operationId"] == "getHistoryTimeline"
    assert {"200", "400", "401", "422"} <= set(
        schema["paths"]["/history/timeline"]["get"]["responses"]
    )


def test_history_timeline_runtime_errors_match_contract_examples() -> None:
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "openapi" / "gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    runtime = create_app(Settings(env="test")).openapi()["paths"]["/api/v1/history/timeline"]["get"]
    frozen = contract["paths"]["/history/timeline"]["get"]
    assert set(runtime["responses"]) == set(frozen["responses"])
    for status in ("400", "422"):
        runtime_example = runtime["responses"][status]["content"]["application/problem+json"][
            "examples"
        ]["problem"]["value"]
        contract_response = contract["components"]["responses"][
            "HistoryInvalidCursor" if status == "400" else "HistoryValidationProblem"
        ]
        contract_example = contract_response["content"]["application/problem+json"]["example"]
        assert {"type", "title", "status", "detail", "instance", "code", "request_id"} <= set(
            runtime_example
        )
        for field in ("type", "title", "status", "detail", "instance", "code"):
            assert runtime_example[field] == contract_example[field]
