"""ADR-0010 F06 recurrence and strict HTTP contract tests (T52-T55)."""

from datetime import date, time
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gutcare.medication.api import CheckinUpdate, PlanCreate, PlanPatch, ScheduleWrite
from gutcare.medication.service import occurrence_dates, parse_rrule, resolve_local_datetime
from gutcare.shared.errors import Problem


def test_plan_dto_rejects_client_scope_and_source_mismatch() -> None:
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {"medication_name": "x", "source_type": "manual", "patient_id": "fake"}
        )


def test_plan_patch_rejects_null_for_nonnullable_fields() -> None:
    with pytest.raises(ValidationError):
        PlanPatch.model_validate({"record_version": 1, "medication_name": None})
    with pytest.raises(ValidationError):
        PlanPatch.model_validate({"record_version": 1, "confirmation_status": None})
    assert PlanPatch.model_validate({"record_version": 1, "dosage_text": None}).dosage_text is None
    with pytest.raises(ValidationError):
        PlanCreate.model_validate(
            {
                "medication_name": "x",
                "source_type": "manual",
                "source_document_id": "019a0000-0000-7000-8000-000000000001",
            }
        )


def test_restricted_rrule_expands_weekdays_and_enforces_count() -> None:
    rule = parse_rrule("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=3")
    assert occurrence_dates(rule, date(2026, 10, 5), date(2026, 11, 1)) == [
        date(2026, 10, 5),
        date(2026, 10, 7),
        date(2026, 10, 19),
    ]
    with pytest.raises(Problem):
        parse_rrule("FREQ=MONTHLY")
    with pytest.raises(Problem):
        parse_rrule("FREQ=DAILY;COUNT=2;UNTIL=20261231")


def test_dst_missing_time_moves_forward_and_ambiguous_uses_first_fold() -> None:
    spring = resolve_local_datetime(date(2026, 3, 8), time(2, 30), "America/New_York")
    assert (spring.hour, spring.minute) == (3, 0)
    fall = resolve_local_datetime(date(2026, 11, 1), time(1, 30), "America/New_York")
    assert fall.fold == 0


def test_timezone_and_taken_timestamp_are_strict() -> None:
    with pytest.raises(ValidationError):
        ScheduleWrite.model_validate(
            {"local_time": "08:00:00", "timezone": "Not/AZone", "valid_from": "2026-01-01"}
        )
    with pytest.raises(ValidationError):
        CheckinUpdate.model_validate({"record_version": 1, "status": "taken"})


def test_openapi_includes_f06_routes_and_problem_details() -> None:
    from gutcare.app import create_app
    from gutcare.config import Settings

    schema = create_app(settings=Settings(env="test")).openapi()
    for path in (
        "/api/v1/medication-plans",
        "/api/v1/medication-plans/{plan_id}",
        "/api/v1/medication-plans/{plan_id}/schedules",
        "/api/v1/medication-schedules/{schedule_id}",
        "/api/v1/medication-checkins/today",
        "/api/v1/medication-checkins/{checkin_id}",
    ):
        assert path in schema["paths"]
    assert (
        "application/problem+json"
        in schema["paths"]["/api/v1/medication-plans"]["post"]["responses"]["422"]["content"]
    )
    assert "404" in schema["paths"]["/api/v1/medication-plans"]["post"]["responses"]
    contract_path = Path(__file__).resolve().parents[2] / "contracts/openapi/gutcare-v1.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    for path in schema["paths"]:
        if path.startswith("/api/v1/medication-"):
            contract_path_value = path.removeprefix("/api/v1")
            assert contract_path_value in contract["paths"]
