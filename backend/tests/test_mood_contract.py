"""F14 frozen API and DTO contract checks."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from gutcare.activity.api import service as get_activity_service
from gutcare.app import create_app
from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.config import Settings
from gutcare.mood.api import MoodPatch, MoodWrite, get_mood_service
from gutcare.mood.service import MoodService
from gutcare.records.api import get_record_service
from gutcare.shared.errors import Problem


def test_mood_routes_and_closed_response_schemas_match_frozen_contract() -> None:
    paths = create_app(Settings(env="test")).openapi()["paths"]
    assert {method for method in ("get", "post") if method in paths["/api/v1/mood-records"]} == {
        "get",
        "post",
    }
    assert {"get", "patch", "delete"} <= set(paths["/api/v1/mood-records/{record_id}"])
    assert paths["/api/v1/mood-records"]["post"]["parameters"][0]["name"] == "Idempotency-Key"
    schemas = create_app(Settings(env="test")).openapi()["components"]["schemas"]
    assert schemas["MoodWrite"]["additionalProperties"] is False
    assert schemas["MoodPatch"]["additionalProperties"] is False
    assert schemas["MoodWrite"]["properties"]["emotion_tags"]["uniqueItems"] is True
    assert schemas["MoodWrite"]["properties"]["emotion_tags"]["maxItems"] == 5
    assert schemas["MoodWrite"]["properties"]["mood_level"]["minimum"] == 1
    assert schemas["MoodWrite"]["properties"]["mood_level"]["maximum"] == 5
    assert "note" not in schemas["MoodSummary"]["properties"]
    assert "note" in schemas["MoodDetail"]["properties"]
    assert schemas["MoodDetail"]["additionalProperties"] is False
    assert "note" in schemas["MoodDetail"]["required"]
    assert "allOf" not in schemas["MoodDetail"]
    assert len(schemas["MoodPatch"]["properties"]["occurred_at"]["anyOf"]) == 1
    create = paths["/api/v1/mood-records"]["post"]
    assert create["operationId"] == "createMoodRecord"
    idem = create["parameters"][0]["schema"]
    assert (idem["minLength"], idem["maxLength"]) == (1, 128)
    assert paths["/api/v1/mood-records"]["get"]["operationId"] == "listMoodRecords"
    assert paths["/api/v1/mood-records/{record_id}"]["get"]["operationId"] == "getMoodRecord"
    assert paths["/api/v1/mood-records/{record_id}"]["patch"]["operationId"] == "patchMoodRecord"
    assert paths["/api/v1/mood-records/{record_id}"]["delete"]["operationId"] == "deleteMoodRecord"
    for method in ("get", "delete"):
        response = paths["/api/v1/mood-records/{record_id}"][method]["responses"]["422"]
        assert "application/problem+json" in response["content"]
        assert "status" in response["content"]["application/problem+json"]["schema"]["properties"]


def test_mood_dtos_reject_out_of_range_duplicate_unknown_and_naive_values() -> None:
    good = {
        "occurred_at": datetime.now(UTC),
        "mood_level": 3,
        "emotion_tags": [],
        "note": "private",
    }
    assert MoodWrite.model_validate(good).mood_level == 3
    controlled = [
        "calm",
        "content",
        "joyful",
        "sad",
        "anxious",
        "irritable",
        "overwhelmed",
        "tired",
        "other",
    ]
    for tag in controlled:
        assert MoodWrite.model_validate({**good, "emotion_tags": [tag]}).emotion_tags == [tag]
    for changes in (
        {"mood_level": 0},
        {"mood_level": True},
        {"emotion_tags": ["calm", "calm"]},
        {"emotion_tags": ["uncontrolled"]},
        {"emotion_tags": ["calm"] * 6},
        {"emotion_tags": ["calm", 4]},
        {"emotion_tags": "calm"},
        {"unknown": 1},
        {"occurred_at": datetime(2026, 1, 1)},
    ):
        with pytest.raises(ValueError):
            MoodWrite.model_validate({**good, **changes})
    with pytest.raises(ValueError):
        MoodPatch.model_validate({"record_version": 1, "mood_level": None})


def test_mood_idempotency_digest_is_keyed_and_note_safe() -> None:
    service = MoodService(sessionmaker(), "independent-mood-idempotency-key-00000001")
    payload = {
        "occurred_at": datetime(2026, 10, 16, 12, 30, tzinfo=UTC),
        "mood_level": 3,
        "emotion_tags": ["calm"],
        "note": "dictionary-guessable private note",
    }
    digest = service._request_hash(payload)
    assert digest == service._request_hash(payload)
    assert digest != service._request_hash({**payload, "note": "different private note"})
    assert payload["note"] not in digest
    assert len(digest) == 64


def test_real_http_mood_routes_select_specialized_router_and_problem_contract() -> None:
    record_id = uuid4()
    now = datetime(2026, 10, 16, 12, 30, tzinfo=UTC)

    class MoodStub:
        calls: list[str] = []

        @staticmethod
        def body():
            return {
                "id": record_id,
                "occurred_at": now,
                "mood_level": 3,
                "emotion_tags": ["calm"],
                "record_version": 1,
                "created_at": now,
                "updated_at": now,
                "note": "private",
            }

        def create(self, *_args):
            self.calls.append("post")
            return self.body()

        def list(self, *_args, **_kwargs):
            self.calls.append("list")
            return {"items": [], "next_cursor": None}

        def get(self, _context, requested):
            self.calls.append("detail")
            if requested != record_id:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self.body()

        def patch(self, *_args):
            self.calls.append("patch")
            return self.body()

        def delete(self, *_args):
            self.calls.append("delete")
            return None

    class GenericStub:
        calls: list[str] = []

        def __getattr__(self, name):
            def invoked(*_args, **_kwargs):
                self.calls.append(name)
                raise AssertionError("generic records route captured mood endpoint")

            return invoked

    class ActivityStub:
        calls: list[str] = []

        @staticmethod
        def body():
            return {"route_owner": "activity", "id": record_id}

        def create(self, *_args):
            self.calls.append("post")
            return self.body()

        def list_activities(self, *_args):
            self.calls.append("list")
            return {"route_owner": "activity", "items": []}

        def get(self, *_args):
            self.calls.append("detail")
            return self.body()

        def update(self, *_args):
            self.calls.append("patch")
            return self.body()

        def delete(self, *_args):
            self.calls.append("delete")

        def timeline(self, *_args):
            raise AssertionError("not part of route-selection test")

        def trends(self, *_args):
            raise AssertionError("not part of route-selection test")

    app = create_app(Settings(env="test"))
    mood, activity, generic = MoodStub(), ActivityStub(), GenericStub()
    app.dependency_overrides[current_auth_context] = lambda: AuthContext(
        user_id=uuid4(), session_id=uuid4()
    )
    app.dependency_overrides[get_mood_service] = lambda: mood
    app.dependency_overrides[get_activity_service] = lambda: activity
    app.dependency_overrides[get_record_service] = lambda: generic
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/mood-records",
                headers={"Idempotency-Key": "route-test"},
                json={
                    "occurred_at": now.isoformat(),
                    "mood_level": 3,
                    "emotion_tags": ["calm"],
                    "note": "private",
                },
            ).status_code
            == 201
        )
        assert client.get("/api/v1/mood-records").status_code == 200
        assert client.get(f"/api/v1/mood-records/{record_id}").status_code == 200
        assert (
            client.patch(
                f"/api/v1/mood-records/{record_id}", json={"record_version": 1, "mood_level": 4}
            ).status_code
            == 200
        )
        assert (
            client.request(
                "DELETE", f"/api/v1/mood-records/{record_id}", json={"record_version": 1}
            ).status_code
            == 204
        )
        invalid = client.get("/api/v1/mood-records/not-a-uuid")
        assert invalid.status_code == 422
        assert invalid.headers["content-type"].startswith("application/problem+json")
        problem = invalid.json()
        assert {"type", "title", "status", "code", "request_id"} <= problem.keys()
        assert problem["status"] == 422
        invalid_delete = client.request(
            "DELETE",
            "/api/v1/mood-records/not-a-uuid",
            json={"record_version": 1},
        )
        assert invalid_delete.status_code == 422
        assert invalid_delete.headers["content-type"].startswith("application/problem+json")
        assert {"type", "title", "status", "code", "request_id"} <= invalid_delete.json().keys()
        hidden = client.get(f"/api/v1/mood-records/{uuid4()}")
        assert hidden.status_code == 404
        assert hidden.headers["content-type"].startswith("application/problem+json")
        assert {"type", "title", "status", "code", "request_id"} <= hidden.json().keys()
        activity_payload = {
            "activity_type": "walking",
            "intensity": "moderate",
            "subjective_feeling": "better",
            "duration_minutes": 30,
            "occurred_at": now.isoformat(),
        }
        created_activity = client.post("/api/v1/activity-records", json=activity_payload)
        assert created_activity.status_code == 201
        assert created_activity.json()["route_owner"] == "activity"
        activity_list = client.get("/api/v1/activity-records")
        assert activity_list.status_code == 200
        assert activity_list.json()["route_owner"] == "activity"
        activity_detail = client.get(f"/api/v1/activity-records/{record_id}")
        assert activity_detail.status_code == 200
        assert activity_detail.json()["route_owner"] == "activity"
        activity_patch = client.patch(
            f"/api/v1/activity-records/{record_id}",
            json={"record_version": 1, "duration_minutes": 40},
        )
        assert activity_patch.status_code == 200
        assert activity_patch.json()["route_owner"] == "activity"
        activity_delete = client.request(
            "DELETE", f"/api/v1/activity-records/{record_id}", json={"record_version": 1}
        )
        assert activity_delete.status_code == 204
    assert mood.calls == ["post", "list", "detail", "patch", "delete", "detail"]
    assert activity.calls == ["post", "list", "detail", "patch", "delete"]
    assert generic.calls == []

    routes = [route.path for route in app.routes if hasattr(route, "path")]
    generic_index = routes.index("/api/v1/{record_type}")
    assert all(
        index < generic_index
        for index, path in enumerate(routes)
        if path.startswith("/api/v1/")
        and path not in {"/api/v1/{record_type}", "/api/v1/{record_type}/{record_id}"}
        and len(path.removeprefix("/api/v1/").split("/")) <= 2
    )
