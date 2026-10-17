"""F11 TrendResponse runtime and frozen OpenAPI contract parity."""

from pathlib import Path
from typing import Any

import yaml

from gutcare.activity.api import TrendResponse
from gutcare.config import Settings
from gutcare.main import create_app


def _contract() -> dict[str, Any]:
    return yaml.safe_load(
        (Path(__file__).parents[2] / "contracts" / "openapi" / "gutcare-v1.yaml").read_text(
            encoding="utf-8"
        )
    )


def test_trends_runtime_and_yaml_status_keys_and_operation_id_match() -> None:
    contract = _contract()
    runtime = create_app(Settings(env="test")).openapi()["paths"]["/api/v1/trends"]["get"]
    frozen = contract["paths"]["/trends"]["get"]
    assert runtime["operationId"] == frozen["operationId"] == "getTrends"
    assert set(runtime["responses"]) == set(frozen["responses"]) == {"200", "401", "422"}


def test_trends_response_has_strict_item_schemas_matching_runtime() -> None:
    contract = _contract()
    runtime_doc = create_app(Settings(env="test")).openapi()
    runtime_schema = runtime_doc["components"]["schemas"]
    frozen_schema = contract["components"]["schemas"]
    expected = {
        "TrendActivity": {"has_data", "items"},
        "TrendActivityItem": {"bucket", "count", "duration_minutes"},
        "TrendStool": {"has_data", "items"},
        "TrendStoolItem": {
            "bucket",
            "has_data",
            "count",
            "bristol_confirmed_count",
            "bristol_unknown_count",
        },
        "TrendSymptom": {"has_data", "items"},
        "TrendSymptomItem": {"bucket", "has_data", "count", "mean_severity", "status"},
        "TrendDiet": {"has_data", "items"},
        "TrendDietItem": {"bucket", "category", "count"},
        "TrendMedication": {"has_data", "items"},
        "TrendMedicationItem": {"bucket", "status", "count"},
    }
    for schema_name, property_names in expected.items():
        frozen = frozen_schema[schema_name]
        runtime = runtime_schema[schema_name]
        assert frozen["additionalProperties"] is False
        assert set(frozen["properties"]) == property_names
        assert set(frozen["required"]) == property_names
        assert runtime["additionalProperties"] is False
        assert set(runtime["properties"]) == property_names
        assert set(runtime["required"]) == property_names

    for name in (
        "activity",
        "stool",
        "symptom",
        "diet_confirmed_categories",
        "medication_checkins",
    ):
        assert (
            contract["components"]["schemas"]["TrendResponse"]["properties"][name]["$ref"]
            == runtime_schema["TrendResponse"]["properties"][name]["$ref"]
        )
        assert (
            contract["components"]["schemas"]["TrendResponse"]["properties"][name]["$ref"].split(
                "/"
            )[-1]
            in expected
        )


def test_trends_examples_match_runtime_and_validate_both_mood_discriminator_states() -> None:
    contract = _contract()
    runtime = create_app(Settings(env="test")).openapi()["paths"]["/api/v1/trends"]["get"]
    frozen = contract["paths"]["/trends"]["get"]
    runtime_examples = runtime["responses"]["200"]["content"]["application/json"]["examples"]
    yaml_examples = frozen["responses"]["200"]["content"]["application/json"]["examples"]
    assert set(runtime_examples) == set(yaml_examples) == {"available", "mood_consent_required"}
    for name in runtime_examples:
        runtime_value = runtime_examples[name]["value"]
        yaml_value = yaml_examples[name]["value"]
        assert runtime_value == yaml_value
        parsed = TrendResponse.model_validate(yaml_value)
        assert parsed.mood.availability == yaml_value["mood"]["availability"]
    assert "buckets" not in yaml_examples["mood_consent_required"]["value"]["mood"]


def test_trends_validation_problem_example_matches_runtime() -> None:
    contract = _contract()
    runtime = create_app(Settings(env="test")).openapi()["paths"]["/api/v1/trends"]["get"][
        "responses"
    ]["422"]["content"]["application/problem+json"]["examples"]["problem"]["value"]
    frozen = contract["components"]["responses"]["TrendValidationProblem"]["content"][
        "application/problem+json"
    ]["example"]
    assert runtime == frozen
    assert runtime["status"] == 422
    assert runtime["instance"] == "/api/v1/trends"
