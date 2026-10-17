"""Direct API tests for fail-closed consent grants and notice-independent withdrawal."""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from gutcare.app import create_app
from gutcare.auth.consent_notices import resolve_current_consent_notice
from gutcare.auth.models import PatientConsent, PatientProfile
from gutcare.auth.security import utc_now
from gutcare.auth.service import AuthContext, AuthService
from gutcare.config import Settings

ROOT = Path(__file__).resolve().parents[2]
NOTICE_ARTIFACT = ROOT / "contracts/consent/consent-notices.json"
MOOD_TYPE = "mood_data_processing"
TOKEN = "access-value-that-is-long"


class _Transaction:
    def __init__(self, database: "_ConsentDatabase") -> None:
        self.database = database

    def __enter__(self) -> "_ConsentDatabase":
        return self.database

    def __exit__(self, *_args: object) -> None:
        return None


class _ConsentDatabase:
    def __init__(self, user_id: UUID) -> None:
        self.profile = PatientProfile(
            id=uuid4(),
            user_id=user_id,
            nickname=None,
            birth_year=1990,
            timezone="Asia/Shanghai",
            profile_version=1,
        )
        self.consents: list[PatientConsent] = []

    def begin(self) -> _Transaction:
        return _Transaction(self)

    def scalar(self, query: Any) -> object | None:
        entity = query.column_descriptions[0]["entity"]
        parameters = query.compile().params
        if entity is PatientProfile:
            return self.profile if parameters.get("user_id_1") == self.profile.user_id else None
        if entity is PatientConsent:
            patient_id = parameters.get("patient_id_1")
            consent_type = parameters.get("consent_type_1")
            matches = [
                item
                for item in self.consents
                if item.patient_id == patient_id and item.consent_type == consent_type
            ]
            return (
                max(matches, key=lambda item: (item.decided_at, str(item.id))) if matches else None
            )
        raise AssertionError(f"Unexpected scalar query entity: {entity}")

    def scalars(self, _query: Any) -> list[object]:
        return []

    def execute(self, _statement: object, _parameters: dict[str, object]) -> None:
        return None

    def add(self, value: object) -> None:
        assert isinstance(value, PatientConsent)
        self.consents.append(value)

    def flush(self) -> None:
        return None


class _AuthServiceFacade:
    def __init__(self, service: AuthService, user_id: UUID) -> None:
        self.service = service
        self.user_id = user_id

    def authenticate_access_token(self, raw_access: str) -> AuthContext:
        if raw_access != TOKEN:
            from gutcare.shared.errors import Problem

            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        return AuthContext(self.user_id, uuid4())

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)


def _artifact() -> dict[str, Any]:
    return json.loads(NOTICE_ARTIFACT.read_text(encoding="utf-8"))


def _settings(path: Path, artifact: dict[str, Any], env: str = "test") -> Settings:
    settings = Settings(env="test", consent_notices_path=path)
    if env != "test":
        settings = settings.model_copy(update={"env": env})
    for consent_type in (
        "health_data_processing",
        "mood_data_processing",
        "mood_ai_sharing",
        "third_party_ai",
    ):
        suffix = consent_type.upper()
        setattr(
            settings,
            f"{consent_type}_policy_version",
            artifact["backend_config"][f"{suffix}_POLICY_VERSION"],
        )
        setattr(
            settings,
            f"{consent_type}_summary_hash",
            artifact["backend_config"][f"{suffix}_SUMMARY_HASH"],
        )
    return settings


def _client(
    tmp_path: Path, artifact: dict[str, Any] | None = None, env: str = "test"
) -> tuple[TestClient, _ConsentDatabase, dict[str, Any]]:
    artifact_value = copy.deepcopy(artifact if artifact is not None else _artifact())
    artifact_path = tmp_path / "consent-notices.json"
    artifact_path.write_text(json.dumps(artifact_value, ensure_ascii=False), encoding="utf-8")
    user_id = uuid4()
    database = _ConsentDatabase(user_id)
    settings = _settings(artifact_path, artifact_value, env)
    service = AuthService(settings, database)  # type: ignore[arg-type]
    app = create_app(settings)
    app.state.auth_service = _AuthServiceFacade(service, user_id)
    return TestClient(app), database, artifact_value


def _grant(client: TestClient, policy_version: str = "test-only-mood-data-v1") -> Any:
    return client.post(
        "/api/v1/patients/me/consents",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"consent_type": MOOD_TYPE, "policy_version": policy_version, "granted": True},
    )


@pytest.mark.parametrize(
    "failure",
    [
        "artifact_missing",
        "disabled",
        "artifact_version",
        "runtime_version",
        "artifact_hash",
        "runtime_hash",
    ],
)
def test_direct_grants_fail_closed_without_exact_enabled_notice(
    tmp_path: Path, failure: str
) -> None:
    artifact = _artifact()
    notice = next(item for item in artifact["notices"] if item["consent_type"] == MOOD_TYPE)
    if failure == "disabled":
        notice["enabled"] = False
    elif failure == "artifact_version":
        notice["policy_version"] = "test-only-mood-data-v2"
    elif failure == "artifact_hash":
        notice["summary_sha256"] = "0" * 64
    client, database, _ = _client(tmp_path, artifact)
    if failure == "artifact_missing":
        client.app.state.auth_service.service._settings.consent_notices_path = (
            tmp_path / "missing.json"
        )
    elif failure == "runtime_version":
        client.app.state.auth_service.service._settings.mood_data_processing_policy_version = (
            "runtime-v2"
        )
    elif failure == "runtime_hash":
        client.app.state.auth_service.service._settings.mood_data_processing_summary_hash = "0" * 64
    response = _grant(client)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "CONSENT_NOTICE_UNAVAILABLE"
    assert database.consents == []


def test_direct_grant_requires_notice_version_and_succeeds_only_on_exact_match(
    tmp_path: Path,
) -> None:
    client, database, _ = _client(tmp_path)
    wrong_version = _grant(client, "stale-version")
    assert wrong_version.status_code == 422
    assert wrong_version.json()["code"] == "VALIDATION_ERROR"
    assert database.consents == []

    response = _grant(client)
    assert response.status_code == 201
    assert len(database.consents) == 1
    assert database.consents[0].metadata_json["notice_summary_hash"] == (
        "7d30d978677482a02db144506c80aed867dcc395b82a96a4a1eda90a87c578e4"
    )


def test_withdrawal_works_without_notice_but_missing_or_revoked_decision_is_409(
    tmp_path: Path,
) -> None:
    client, database, _ = _client(tmp_path)
    profile = database.profile
    database.consents.append(
        PatientConsent(
            patient_id=profile.id,
            consent_type=MOOD_TYPE,
            document_version="test-only-mood-data-v1",
            granted=True,
            decided_at=utc_now(),
            revoked_at=None,
            metadata_json={
                "notice_summary_hash": (
                    "7d30d978677482a02db144506c80aed867dcc395b82a96a4a1eda90a87c578e4"
                )
            },
        )
    )
    client.app.state.auth_service.service._settings.consent_notices_path = tmp_path / "missing.json"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = {"consent_type": MOOD_TYPE, "policy_version": "test-only-mood-data-v1", "granted": False}
    revoked = client.post("/api/v1/patients/me/consents", headers=headers, json=body)
    assert revoked.status_code == 201
    assert revoked.json()["granted"] is False
    assert database.consents[-1].metadata_json == {
        "channel": "mobile_app",
        "notice_summary_hash": database.consents[0].metadata_json["notice_summary_hash"],
    }
    repeated = client.post("/api/v1/patients/me/consents", headers=headers, json=body)
    assert repeated.status_code == 409
    assert repeated.headers["content-type"].startswith("application/problem+json")
    assert repeated.json()["code"] == "CONSENT_NOT_ACTIVE"
    assert len(database.consents) == 2


def test_production_rejects_test_only_even_if_mislabelled_approved(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["legal_approval_status"] = "approved"
    client, database, _ = _client(tmp_path, artifact, env="production")
    response = _grant(client)
    assert response.status_code == 503
    assert response.json()["code"] == "CONSENT_NOTICE_UNAVAILABLE"
    assert database.consents == []


def test_production_accepts_only_the_explicit_approved_classification(tmp_path: Path) -> None:
    artifact = _artifact()
    artifact["artifact_classification"] = "production_approved"
    artifact["legal_approval_status"] = "approved"
    client, database, _ = _client(tmp_path, artifact, env="production")
    response = _grant(client)
    assert response.status_code == 201
    assert len(database.consents) == 1
    assert resolve_current_consent_notice(client.app.state.settings, MOOD_TYPE) is not None


def test_runtime_and_contract_declare_consent_not_active_problem() -> None:
    openapi = create_app(Settings(env="test")).openapi()
    response = openapi["paths"]["/api/v1/patients/me/consents"]["post"]["responses"]["409"]
    example = response["content"]["application/problem+json"]["examples"]["problem"]["value"]
    assert example["code"] == "CONSENT_NOT_ACTIVE"
    contract_path = ROOT / "contracts/openapi/gutcare-v1.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    consent_post = contract["paths"]["/patients/me/consents"]["post"]
    assert (
        consent_post["responses"]["409"]["content"]["application/problem+json"]["examples"][
            "consentNotActive"
        ]["value"]["code"]
        == "CONSENT_NOT_ACTIVE"
    )
