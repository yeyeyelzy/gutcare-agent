"""F07 DTO and F11 cursor contract checks (T87/T88)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gutcare.activity.api import ActivityPatch, ActivityWrite
from gutcare.activity.service import ActivityService
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
        "medication_checkin",
        "activity_record",
        "advice",
    ]
