import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from gutcare.files.api import (
    AgentCandidate,
    AgentCandidateSubmission,
    CandidateDecisionRequest,
    MedicalDocumentCreate,
    MedicalDocumentPatch,
    agent_router,
    router,
)
from gutcare.files.service import FileService, _canonical_decimal
from gutcare.shared.errors import Problem


def test_medical_document_patch_is_partial_and_not_create_dto() -> None:
    patch = MedicalDocumentPatch(record_version=3, notes=None)
    assert patch.record_version == 3
    assert patch.model_dump(exclude={"record_version"}, exclude_unset=True) == {"notes": None}
    schema = MedicalDocumentPatch.model_json_schema()
    assert schema["required"] == ["record_version"]
    assert "file_object_id" not in schema["properties"]
    assert "processing_mode" not in schema["properties"]
    assert schema["properties"]["document_type"]["type"] == "string"


def test_medical_document_patch_rejects_explicit_null_for_non_nullable_type() -> None:
    with pytest.raises(ValidationError):
        MedicalDocumentPatch(record_version=1, document_type=None)  # type: ignore[arg-type]


def test_document_create_remains_a_distinct_required_contract() -> None:
    schema = MedicalDocumentCreate.model_json_schema()
    assert "file_object_id" in schema["required"]
    assert "processing_mode" in schema["required"]


def test_complete_upload_api_contract_documents_scanner_unavailable() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/api/v1/files/uploads/{upload_id}/complete"]["post"]
    assert "503" in operation["responses"]


def _candidate() -> dict[str, object]:
    return {
        "field_code": "diagnosis",
        "value_type": "diagnosis",
        "value": {"text": "IBS", "certainty": "suspected"},
        "unit": None,
        "confidence": 0.72,
        "uncertainty": "wording is unclear",
        "source_locator": {
            "page": 1,
            "char_start": 4,
            "char_end": 14,
            "bbox": [0.1, 0.2, 0.4, 0.1],
        },
        "excerpt": "考虑 IBS",
    }


def test_t60_candidate_contract_accepts_typed_suspected_diagnosis_without_upgrading_it() -> None:
    candidate = _candidate()
    FileService.validate_medical_candidate(candidate)
    assert AgentCandidate.model_validate(candidate).value["certainty"] == "suspected"


@pytest.mark.parametrize("result", [float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"])
def test_t104_test_result_rejects_non_finite_numbers(result: object) -> None:
    candidate = {
        "field_code": "test_result",
        "value_type": "object",
        "value": {"result": result, "unit": "mg/L"},
        "unit": "mg/L",
        "confidence": 0.8,
        "uncertainty": None,
        "source_locator": {"page": 1, "char_start": 0, "char_end": 1},
        "excerpt": "result",
    }
    with pytest.raises(Problem):
        FileService.validate_medical_candidate(candidate)


@pytest.mark.parametrize("unit", ["MG/L", " mg/l ", "ｍｇ／Ｌ"])
def test_t104_test_result_unit_comparison_is_normalized(unit: str) -> None:
    candidate = {
        "field_code": "test_result",
        "value_type": "object",
        "value": {"result": "5.00", "unit": unit},
        "unit": "mg/L",
        "confidence": 0.8,
        "uncertainty": None,
        "source_locator": {"page": 1, "char_start": 0, "char_end": 1},
        "excerpt": "result",
    }
    FileService.validate_medical_candidate(candidate)


def test_t104_decimal_canonicalizer_preserves_arbitrary_precision_without_expansion() -> None:
    assert _canonical_decimal(5) == _canonical_decimal(5.0) == _canonical_decimal("5.00")
    assert _canonical_decimal("1234567890123456789012345678901") != _canonical_decimal(
        "1234567890123456789012345678902"
    )
    assert _canonical_decimal("1.0000000000000000000000000001") != _canonical_decimal(
        "1.0000000000000000000000000002"
    )
    huge = _canonical_decimal("1e999999999")
    assert huge == "1e999999999" and len(huge) < 20


def test_t103_parse_outcome_cardinality_and_reason_codes() -> None:
    callback = "00000000-0000-4000-8000-000000000001"
    candidate = _candidate()
    assert (
        AgentCandidateSubmission.model_validate(
            {"callback_id": callback, "candidates": [candidate]}
        ).parse_outcome
        is None
    )  # legacy non-empty callbacks are service-mapped to extracted
    assert AgentCandidateSubmission.model_validate(
        {
            "callback_id": callback,
            "parse_outcome": "no_supported_facts",
            "reason_code": "no_supported_fields",
            "candidates": [],
        }
    )
    assert AgentCandidateSubmission.model_validate(
        {
            "callback_id": callback,
            "parse_outcome": "insufficient_quality",
            "reason_code": "low_quality_scan",
            "candidates": [],
        }
    )
    for value in (
        {"callback_id": callback, "candidates": []},
        {"callback_id": callback, "parse_outcome": "extracted", "candidates": []},
        {
            "callback_id": callback,
            "parse_outcome": "no_supported_facts",
            "reason_code": "low_quality_scan",
            "candidates": [],
        },
        {
            "callback_id": callback,
            "parse_outcome": "insufficient_quality",
            "reason_code": "unbounded text not allowed",
            "candidates": [],
        },
    ):
        with pytest.raises(ValidationError):
            AgentCandidateSubmission.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        {"field_code": "patient_id"},
        {"value_type": "string"},
        {"value": {"text": "IBS", "certainty": "confirmed_by_model"}},
        {"confidence": 1.1},
        {"source_locator": {"char_start": 9, "char_end": 2}},
        {"source_locator": {"bbox": [0, 0, 4, 0]}},
        {"excerpt": "x" * 501},
    ],
)
def test_t62_candidate_schema_rejects_malformed_values_and_evidence(
    change: dict[str, object],
) -> None:
    candidate = _candidate()
    candidate.update(change)
    with pytest.raises((Problem, ValidationError)):
        FileService.validate_medical_candidate(candidate)
        AgentCandidate.model_validate(candidate)


def test_t63_decision_api_requires_explicit_single_field_choice_and_version() -> None:
    schema = CandidateDecisionRequest.model_json_schema()
    assert schema["required"] == ["decision", "record_version"]
    assert "additionalProperties" not in schema or schema["additionalProperties"] is False


def test_t65_patient_decision_endpoint_is_204_without_response_body() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/api/v1/medical-field-candidates/{candidate_id}/decision"][
        "post"
    ]
    assert "204" in operation["responses"]
    assert "content" not in operation["responses"]["204"]


def test_t61_internal_agent_contract_is_task_scoped_and_uses_service_bearer() -> None:
    app = FastAPI()
    app.include_router(agent_router)
    schema = app.openapi()
    inputs = schema["paths"]["/internal/v1/agent/medical-parse-requests/{request_id}/inputs"]["get"]
    callback = schema["paths"]["/internal/v1/agent/medical-parse-requests/{request_id}/candidates"][
        "post"
    ]
    assert "request_id" in str(inputs["parameters"])
    assert "patient_id" not in str(inputs["responses"])
    assert callback["operationId"] == "submitMedicalFieldCandidates"
    callback_schema = schema["components"]["schemas"]["AgentCandidateSubmission"]
    assert callback_schema["properties"]["parse_outcome"]["anyOf"][0]["enum"] == [
        "extracted",
        "no_supported_facts",
        "insufficient_quality",
    ]


def test_t64_source_locator_requires_a_real_page_range_or_normalized_box() -> None:
    candidate = _candidate()
    candidate["source_locator"] = {"bbox": [0.9, 0.9, 0.4, 0.4]}
    with pytest.raises(Problem):
        FileService.validate_medical_candidate(candidate)
