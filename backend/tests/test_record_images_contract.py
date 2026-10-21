"""Runtime contract checks for the frozen F03/F04 image boundary."""

from pathlib import Path

import yaml

from gutcare.app import create_app
from gutcare.config import Settings
from gutcare.records.api import validate_payload
from gutcare.records.image_worker import CandidateSubmission
from gutcare.shared.errors import Problem

ROOT = Path(__file__).resolve().parents[2]


def test_image_routes_match_frozen_public_operation_ids() -> None:
    runtime = create_app(settings=Settings(env="test")).openapi()
    contract = yaml.safe_load(
        (ROOT / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    operations = {
        operation["operationId"]
        for path, path_item in contract["paths"].items()
        if path.startswith(
            (
                "/dietary-records/",
                "/stool-records/",
                "/record-images/",
                "/record-image-recognition",
                "/record-image-candidates/",
            )
        )
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    runtime_operations = {
        operation["operationId"]
        for path, path_item in runtime["paths"].items()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert {
        "listDietRecordImages",
        "attachDietRecordImage",
        "listStoolRecordImages",
        "attachStoolRecordImage",
        "deleteRecordImage",
        "createRecordImageDownloadGrant",
        "getRecordImageRecognitionDisclosure",
        "acknowledgeRecordImageRecognitionDisclosure",
        "createDietImageRecognitionRequest",
        "createStoolImageRecognitionRequest",
        "getRecordImageRecognitionRequest",
        "retryRecordImageRecognitionRequest",
        "decideRecordImageCandidate",
    } <= operations
    implemented = {
        "listDietRecordImages",
        "attachDietRecordImage",
        "listStoolRecordImages",
        "attachStoolRecordImage",
        "deleteRecordImage",
        "createRecordImageDownloadGrant",
        "getRecordImageRecognitionDisclosure",
        "acknowledgeRecordImageRecognitionDisclosure",
        "createDietImageRecognitionRequest",
        "createStoolImageRecognitionRequest",
        "getRecordImageRecognitionRequest",
        "retryRecordImageRecognitionRequest",
        "decideRecordImageCandidate",
    }
    assert implemented <= operations
    assert implemented <= runtime_operations
    artifact_attachment = contract["components"]["schemas"]["RecordImageAttachment"]
    assert set(artifact_attachment["required"]) == {
        "id",
        "record_id",
        "position",
        "record_version",
        "image_set_version",
        "file_status",
        "created_at",
    }
    assert artifact_attachment["properties"]["file_status"]["enum"] == [
        "available",
        "unavailable",
    ]
    attachment = runtime["components"]["schemas"]["RecordImageAttachmentResponse"]
    assert set(attachment["required"]) == {
        "id",
        "record_id",
        "position",
        "record_version",
        "image_set_version",
        "file_status",
        "created_at",
    }


def test_worker_routes_match_frozen_agent_contract() -> None:
    runtime = create_app(settings=Settings(env="test")).openapi()
    contract = yaml.safe_load((ROOT / "contracts/agent/agent-v1.yaml").read_text(encoding="utf-8"))
    operations = {
        operation["operationId"]: path
        for path, path_item in contract["paths"].items()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    runtime_operations = {
        operation["operationId"]: path
        for path, path_item in runtime["paths"].items()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    worker_operations = {
        "claimRecordImageRecognitionRequest",
        "getRecordImageRecognitionInput",
        "readRecordImageRecognitionImage",
        "submitRecordImageRecognitionCandidates",
        "failRecordImageRecognition",
    }
    assert worker_operations <= operations.keys()
    assert worker_operations <= runtime_operations.keys()
    for operation_id in worker_operations:
        assert runtime_operations[operation_id] == f"/internal/v1{operations[operation_id]}"


def test_agent_callback_schema_rejects_non_frozen_candidate_fields() -> None:
    valid = {
        "callback_id": "019a0000-0000-7000-8000-000000000041",
        "record_version": 3,
        "image_set_version": 2,
        "schema_version": "1.0",
        "images": [
            {
                "attachment_id": "019a0000-0000-7000-8000-000000000022",
                "image_quality": "usable",
                "candidates": [
                    {
                        "candidate_id": "019a0000-0000-7000-8000-000000000031",
                        "attachment_id": "019a0000-0000-7000-8000-000000000022",
                        "candidate_group_key": "019a0000-0000-7000-8000-000000000071",
                        "candidate_type": "food_name",
                        "value": "rice",
                        "confidence_band": "medium",
                        "uncertainty_code": "other",
                    }
                ],
            }
        ],
    }
    assert CandidateSubmission.model_validate(valid).images[0].candidates
    invalid = {
        **valid,
        "images": [
            {
                **valid["images"][0],
                "candidates": [{**valid["images"][0]["candidates"][0], "visual_tag": "red"}],
            }
        ],
    }
    try:
        CandidateSubmission.model_validate(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("unfrozen candidate fields must be rejected")


def test_legacy_image_object_id_is_not_a_write_payload() -> None:
    try:
        validate_payload(
            "diet-records",
            {"text_description": "meal", "image_object_id": "00000000-0000-4000-8000-000000000001"},
        )
    except Problem as error:
        assert error.status == 422
        assert error.code == "VALIDATION_ERROR"
    else:
        raise AssertionError("legacy image_object_id must not be accepted for new writes")


def test_disclosure_endpoint_is_fail_closed_without_runtime_notice_configuration() -> None:
    app = create_app(settings=Settings(env="test"))
    schema = app.openapi()
    route = schema["paths"]["/api/v1/record-image-recognition-disclosures"]["get"]
    assert route["operationId"] == "getRecordImageRecognitionDisclosure"
    assert "purpose" in {p["name"] for p in route["parameters"]}
