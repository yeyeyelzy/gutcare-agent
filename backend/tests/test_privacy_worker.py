import json
import zipfile
from io import BytesIO
from uuid import uuid4

import pytest

from gutcare.auth.service import AuthContext
from gutcare.privacy.api import _limit_status_checks
from gutcare.privacy.service import (
    EXPORT_CATEGORIES,
    MAX_EXPORT_BYTES,
    MAX_EXPORT_CIPHERTEXT_BYTES,
    PrivacyService,
    _validate_export_size,
)
from gutcare.privacy.worker import DELETE_PHASES, PrivacyWorker, scan_export_zip
from gutcare.shared.errors import Problem


def _archive(data: dict[str, object], entry_name: str = "data.json") -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(entry_name, json.dumps(data))
        if entry_name != "data.json":
            archive.writestr("data.json", "{}")
    return buffer.getvalue()


def test_export_scan_accepts_whitelisted_shape_and_safe_path() -> None:
    scan_export_zip(_archive({"datasets": {"profile": [{"nickname": "patient"}]}}))


@pytest.mark.parametrize(
    "payload,entry_name",
    [
        ({"datasets": {"tasks": [{"prompt": "must not export"}]}}, "data.json"),
        ({"datasets": {"files": [{"object_key": "private/path"}]}}, "data.json"),
        ({"datasets": {}}, "../data.json"),
    ],
)
def test_export_scan_rejects_forbidden_keys_and_unsafe_paths(
    payload: dict[str, object], entry_name: str
) -> None:
    with pytest.raises(ValueError):
        scan_export_zip(_archive(payload, entry_name))


def test_deletion_ledger_has_ordered_phases_and_preserves_global_rules() -> None:
    assert tuple(DELETE_PHASES) == ("purge_derived", "purge_health")
    tables = {table for phase in DELETE_PHASES.values() for table in phase}
    assert "health.patient_notification" in tables
    assert "analysis.analysis_task" in tables
    assert "health.medical_document" in tables
    ordered = list(DELETE_PHASES["purge_health"])
    assert (
        ordered.index("analysis.record_image_decision")
        < ordered.index("analysis.record_image_candidate")
        < ordered.index("analysis.record_image_recognition_request")
    )
    assert ordered.index("health.diet_record_image") < ordered.index("health.file_object")
    assert ordered.index("health.stool_record_image") < ordered.index("health.file_object")
    assert "health.mood_record" in tables
    assert "privacy.mood_purge_queue" in tables
    assert "safety.risk_rule" not in tables


def test_diet_and_stool_export_categories_query_record_image_decisions_and_attachments() -> None:
    class EmptyResult:
        def mappings(self) -> "EmptyResult":
            return self

        def all(self) -> list[object]:
            return []

    class QueryRecorder:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def execute(self, statement: object, _params: object = None) -> EmptyResult:
            self.queries.append(str(statement))
            return EmptyResult()

    class NoStorage:
        pass

    db = QueryRecorder()
    worker = PrivacyWorker(None, NoStorage(), "bucket", b"x" * 32)  # type: ignore[arg-type]
    diet_data, diet_attachments = worker._export_payload(db, uuid4(), ["diet"])  # type: ignore[arg-type]
    assert "diet_image_decisions" in diet_data
    assert "diet_record_images" in diet_data
    assert not diet_attachments
    assert any("analysis.record_image_decision" in sql for sql in db.queries)
    assert any("health.diet_record_image" in sql for sql in db.queries)

    db.queries.clear()
    stool_data, stool_attachments = worker._export_payload(db, uuid4(), ["stool"])  # type: ignore[arg-type]
    assert "stool_image_decisions" in stool_data
    assert "stool_record_images" in stool_data
    assert not stool_attachments
    assert any("health.stool_record_image" in sql for sql in db.queries)


def test_mood_is_an_explicit_export_category() -> None:
    assert "mood" in EXPORT_CATEGORIES


def test_export_is_disabled_at_preview_when_kek_is_missing() -> None:
    service = PrivacyService(None, "pepper", encryption_key=None)  # type: ignore[arg-type]
    with pytest.raises(Problem) as error:
        service.create_export_preview(AuthContext(uuid4(), uuid4()), ["profile"])
    assert error.value.status == 503


def test_receipt_status_endpoint_rate_limiter_returns_429() -> None:
    key = f"privacy-test-{uuid4()}"
    for _ in range(20):
        _limit_status_checks(key)
    with pytest.raises(Problem) as error:
        _limit_status_checks(key)
    assert error.value.status == 429


def test_export_envelope_size_is_bounded_before_and_after_decryption() -> None:
    _validate_export_size(MAX_EXPORT_CIPHERTEXT_BYTES, MAX_EXPORT_BYTES)
    with pytest.raises(ValueError):
        _validate_export_size(MAX_EXPORT_CIPHERTEXT_BYTES + 1)
    with pytest.raises(ValueError):
        _validate_export_size(MAX_EXPORT_CIPHERTEXT_BYTES, MAX_EXPORT_BYTES + 1)
