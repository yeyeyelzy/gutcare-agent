"""F12 patient API DTO and frozen OpenAPI contract checks (T80/T81/T84)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gutcare.notifications.api import BatchReadBody, PreferenceBody


def test_notification_preferences_are_strict_and_timezone_aware() -> None:
    body = PreferenceBody.model_validate(
        {
            "ordinary_in_app_enabled": False,
            "quiet_start": "22:00:00",
            "quiet_end": "07:00:00",
            "timezone": "Asia/Shanghai",
        }
    )
    assert body.quiet_start is not None
    for invalid in (
        {
            "ordinary_in_app_enabled": False,
            "quiet_start": "22:00",
            "quiet_end": None,
            "timezone": "UTC",
        },
        {
            "ordinary_in_app_enabled": True,
            "quiet_start": None,
            "quiet_end": None,
            "timezone": "Not/AZone",
        },
        {
            "ordinary_in_app_enabled": True,
            "quiet_start": None,
            "quiet_end": None,
            "timezone": "UTC",
            "push_enabled": True,
        },
    ):
        with pytest.raises(ValidationError):
            PreferenceBody.model_validate(invalid)


def test_notification_batch_read_rejects_duplicate_ids() -> None:
    from uuid import uuid4

    ident = uuid4()
    with pytest.raises(ValidationError):
        BatchReadBody.model_validate({"notification_ids": [ident, ident]})


def test_notification_openapi_exposes_only_sanitized_dtos() -> None:
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "openapi" / "gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = contract["paths"]
    expected = {
        "/notifications",
        "/notifications/unread-count",
        "/notifications/preferences",
        "/notifications/read-batch",
        "/notifications/{notification_id}",
        "/notifications/{notification_id}/read",
    }
    assert expected <= set(paths)
    dto = contract["components"]["schemas"]["PatientNotification"]
    assert "body" not in dto["properties"]
    assert "title" not in dto["properties"]
    assert dto["additionalProperties"] is False
    assert "risk" in dto["properties"]["category"]["enum"]
