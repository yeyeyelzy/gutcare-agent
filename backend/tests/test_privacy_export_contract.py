from __future__ import annotations

from pathlib import Path

import yaml

from gutcare.app import create_app
from gutcare.config import Settings


def test_f13_export_runtime_operations_match_the_frozen_six_operation_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/openapi/gutcare-v1.yaml").read_text(encoding="utf-8")
    )
    runtime = create_app(Settings(env="test")).openapi()
    expected = {
        ("/privacy/exports", "post"): "createPrivacyExport",
        ("/privacy/exports", "get"): "listPrivacyExports",
        ("/privacy/exports/{export_id}", "get"): "getPrivacyExport",
        ("/privacy/exports/{export_id}", "post"): "confirmPrivacyExport",
        ("/privacy/exports/{export_id}/cancel", "post"): "cancelPrivacyExport",
        ("/privacy/exports/download", "get"): "downloadPrivacyExport",
    }
    success_status = {
        ("/privacy/exports", "post"): "201",
        ("/privacy/exports", "get"): "200",
        ("/privacy/exports/{export_id}", "get"): "200",
        ("/privacy/exports/{export_id}", "post"): "202",
        ("/privacy/exports/{export_id}/cancel", "post"): "204",
        ("/privacy/exports/download", "get"): "200",
    }
    for (path, method), operation_id in expected.items():
        assert contract["paths"][path][method]["operationId"] == operation_id
        runtime_operation = runtime["paths"][f"/api/v1{path}"][method]
        assert runtime_operation["operationId"] == operation_id
        assert set(runtime_operation["responses"]) == set(
            contract["paths"][path][method]["responses"]
        ), operation_id
        assert success_status[(path, method)] in contract["paths"][path][method]["responses"]
        for response in contract["paths"][path][method]["responses"].values():
            if "$ref" in response:
                component_name = response["$ref"].rsplit("/", 1)[-1]
                assert (
                    "application/problem+json"
                    in contract["components"]["responses"][component_name]["content"]
                )
    path_validation = contract["components"]["responses"]["PrivacyExportPathProblem422"]
    yaml_example = path_validation["content"]["application/problem+json"]["example"]
    example_fields = {"type", "title", "status", "detail", "instance", "code", "request_id"}
    assert {key: yaml_example[key] for key in example_fields} == {
        "type": "https://gutcare.invalid/problems/validation_error",
        "title": "Request validation failed",
        "status": 422,
        "detail": "导出 ID 格式无效。",
        "instance": "/api/v1/privacy/exports/not-a-uuid",
        "code": "VALIDATION_ERROR",
        "request_id": "00000000-0000-4000-8000-000000000422",
    }
    for path, method in (
        ("/privacy/exports/{export_id}", "get"),
        ("/privacy/exports/{export_id}", "post"),
        ("/privacy/exports/{export_id}/cancel", "post"),
    ):
        runtime_example = runtime["paths"][f"/api/v1{path}"][method]["responses"]["422"]["content"][
            "application/problem+json"
        ]["examples"]["problem"]["value"]
        assert {key: runtime_example[key] for key in example_fields} == {
            key: yaml_example[key] for key in example_fields
        }

    download = contract["paths"]["/privacy/exports/download"]["get"]
    assert download["security"] == []
    assert "X-Export-Capability" in [parameter["name"] for parameter in download["parameters"]]
    assert "application/zip" in download["responses"]["200"]["content"]
    assert (
        "application/zip"
        in runtime["paths"]["/api/v1/privacy/exports/download"]["get"]["responses"]["200"][
            "content"
        ]
    )

    schemas = contract["components"]["schemas"]
    assert schemas["PrivacyExportStatus"]["enum"] == [
        "preview",
        "pending",
        "processing",
        "ready",
        "failed",
        "cancelled",
        "expired",
    ]
    assert schemas["PrivacyExportCategory"]["enum"] == [
        "profile",
        "consents",
        "medical_documents",
        "files",
        "diet",
        "stool",
        "symptoms",
        "mood",
        "medication",
        "activity",
        "analysis",
        "advice",
        "alerts",
        "notifications",
    ]
    assert "download_capability" in schemas["PrivacyExportDetail"]["required"]
    assert "created_at" in schemas["PrivacyExportSummary"]["required"]
    assert schemas["PrivacyExportRequest"]["required"] == ["categories"]
    runtime_schemas = runtime["components"]["schemas"]
    assert (
        runtime_schemas["ExportRequest"]["properties"]["categories"]["items"]["enum"]
        == schemas["PrivacyExportCategory"]["enum"]
    )
    assert (
        runtime_schemas["ExportStatusResponse"]["properties"]["status"]["enum"]
        == schemas["PrivacyExportStatus"]["enum"]
    )
