"""Patient-facing F08 operation, DTO, and opaque-cursor contracts."""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from gutcare.analysis.api import AnalysisTask, AnalysisTaskPage, AnalysisTaskPreview
from gutcare.analysis.service import AnalysisService
from gutcare.app import create_app
from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.config import Settings
from gutcare.shared.errors import Problem

OPERATIONS = {
    ("/analysis-tasks/preview", "get"): (
        "previewAnalysisTask",
        {"200", "401", "404", "409", "422", "500"},
        "AnalysisTaskPreview",
    ),
    ("/analysis-tasks", "post"): (
        "createAnalysisTask",
        {"202", "401", "404", "409", "422", "500"},
        "AnalysisTask",
    ),
    ("/analysis-tasks", "get"): (
        "listAnalysisTasks",
        {"200", "400", "401", "404", "422", "500"},
        "AnalysisTaskPage",
    ),
    ("/analysis-tasks/{task_id}", "get"): (
        "getAnalysisTask",
        {"200", "401", "404", "422", "500"},
        "AnalysisTask",
    ),
    ("/analysis-tasks/{task_id}/cancel", "post"): (
        "cancelAnalysisTask",
        {"200", "401", "404", "409", "422", "500"},
        "AnalysisTask",
    ),
    ("/analysis-tasks/{task_id}/retry", "post"): (
        "retryAnalysisTask",
        {"202", "401", "404", "409", "422", "500"},
        "AnalysisTask",
    ),
}


def _value(response: dict) -> dict:
    content = response["content"]["application/json"]
    if "examples" in content:
        return next(iter(content["examples"].values()))["value"]
    return content["example"]


def test_patient_analysis_runtime_and_yaml_operation_status_schema_and_examples_match() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    app = create_app(Settings(env="test"))
    runtime = app.openapi()
    for (path, method), (operation_id, expected_statuses, response_schema) in OPERATIONS.items():
        yaml_operation = contract["paths"][path][method]
        runtime_operation = runtime["paths"][f"/api/v1{path}"][method]
        assert yaml_operation["operationId"] == runtime_operation["operationId"] == operation_id
        assert (
            set(yaml_operation["responses"])
            == set(runtime_operation["responses"])
            == expected_statuses
        )
        success_status = (
            "202"
            if method == "post" and operation_id in {"createAnalysisTask", "retryAnalysisTask"}
            else "200"
        )
        yaml_success = yaml_operation["responses"][success_status]
        runtime_success = runtime_operation["responses"][success_status]
        expected_ref = f"#/components/schemas/{response_schema}"
        assert yaml_success["content"]["application/json"]["schema"]["$ref"] == expected_ref
        assert runtime_success["content"]["application/json"]["schema"]["$ref"] == expected_ref
        yaml_example = _value(yaml_success)
        runtime_example = _value(runtime_success)
        assert isinstance(yaml_example, dict) and isinstance(runtime_example, dict)
        model = {
            "AnalysisTask": AnalysisTask,
            "AnalysisTaskPage": AnalysisTaskPage,
            "AnalysisTaskPreview": AnalysisTaskPreview,
        }[response_schema]
        model.model_validate(yaml_example)
        assert "patient_id" not in json.dumps(runtime_example).lower()
        for status, response in yaml_operation["responses"].items():
            if status in {"200", "202", "204"}:
                continue
            if "$ref" in response:
                problem_response = contract["components"]["responses"][
                    response["$ref"].split("/")[-1]
                ]
            else:
                problem_response = response
            example = next(
                iter(problem_response["content"]["application/problem+json"]["examples"].values())
            )["value"]
            assert example["status"] == int(status)
            assert example["request_id"]
            assert "patient_id" not in example


def test_cursor_hides_patient_uuid_and_fails_closed_for_tamper_patient_or_limit() -> None:
    patient_a = uuid4()
    patient_b = uuid4()
    task_id = uuid4()
    service = AnalysisService(sessions=None, cursor_secret="test-only-cursor-secret")  # type: ignore[arg-type]
    task = SimpleNamespace(id=task_id, created_at=datetime(2026, 10, 1, tzinfo=UTC))
    cursor = service._encode_task_cursor(patient_a, 2, task)
    packed = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = json.loads(packed[:-32])
    assert "patient_id" not in payload
    assert "patient_scope" in payload
    assert str(patient_a) not in packed.decode("utf-8", errors="ignore")
    assert service._decode_task_cursor(cursor, patient_a, 2) == (task.created_at, task_id)
    for changed_cursor, changed_patient, changed_limit in (
        (cursor[:-1] + ("A" if cursor[-1] != "A" else "B"), patient_a, 2),
        (cursor, patient_b, 2),
        (cursor, patient_a, 3),
    ):
        with pytest.raises(Problem) as error:
            service._decode_task_cursor(changed_cursor, changed_patient, changed_limit)
        assert error.value.status == 400
        assert error.value.code == "INVALID_CURSOR"
        assert cursor not in error.value.detail


def test_cursor_rejects_noncanonical_base64url_alias_without_disclosure() -> None:
    patient_id = uuid4()
    task_id = uuid4()
    service = AnalysisService(sessions=None, cursor_secret="test-only-cursor-secret")  # type: ignore[arg-type]
    task = SimpleNamespace(id=task_id, created_at=datetime(2026, 10, 1, tzinfo=UTC))
    cursor_limit = next(
        limit
        for limit in range(1, 101)
        if len(service._encode_task_cursor(patient_id, limit, task)) % 4 in {2, 3}
    )
    cursor = service._encode_task_cursor(patient_id, cursor_limit, task)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    last_index = alphabet.index(cursor[-1])
    alias = f"{cursor[:-1]}{alphabet[last_index | 1]}"
    padding = "=" * (-len(cursor) % 4)
    canonical_bytes = base64.urlsafe_b64decode(cursor + padding)

    assert alias != cursor
    assert base64.urlsafe_b64decode(alias + padding) == canonical_bytes
    assert service._decode_task_cursor(cursor, patient_id, cursor_limit) == (
        task.created_at,
        task_id,
    )
    with pytest.raises(Problem) as error:
        service._decode_task_cursor(alias, patient_id, cursor_limit)
    assert error.value.status == 400
    assert error.value.code == "INVALID_CURSOR"
    assert error.value.title == "Analysis task cursor is invalid"
    assert not error.value.detail
    assert alias not in str(error.value)


def test_analysis_list_invalid_cursor_is_rfc9457_and_does_not_echo_cursor() -> None:
    app = create_app(Settings(env="test"))

    class InvalidCursorService:
        def list(self, context: AuthContext, limit: int, cursor: str | None) -> dict:
            raise Problem(400, "INVALID_CURSOR", "Analysis task cursor is invalid")

    app.state.analysis_service = InvalidCursorService()
    app.dependency_overrides[current_auth_context] = lambda: AuthContext(
        user_id=uuid4(), session_id=uuid4()
    )
    cursor = "tampered-cursor-payload"
    with TestClient(app) as client:
        response = client.get("/api/v1/analysis-tasks", params={"cursor": cursor})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_CURSOR"
    assert cursor not in response.text
