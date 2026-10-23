"""Contract-level tests for the F01 email authentication routes."""

from pathlib import Path
from uuid import UUID, uuid4  # noqa: I001 - gutcare.app preloads logging before FastAPI on Python 3.13

import pytest
import yaml
from fastapi.testclient import TestClient

from gutcare.app import create_app
from gutcare.auth.api import AuthContext
from gutcare.auth.service import (
    ConsentDecisionData,
    ConsentStatusData,
    PatientProfileData,
    TokenPair,
)
from gutcare.config import Settings
from gutcare.shared.errors import Problem


class FakeAuthService:
    def __init__(self) -> None:
        self.registered: list[dict[str, object]] = []
        self.verified: list[str] = []
        self.logged_out: list[AuthContext] = []
        self.profile = PatientProfileData(
            id=uuid4(), nickname=None, birth_year=1990, timezone="Asia/Shanghai", profile_version=1
        )
        self.profile_changes: list[dict[str, object]] = []
        self.consent_decisions: list[tuple[str, str, bool]] = []
        self.consent_statuses: list[ConsentStatusData] = [
            ConsentStatusData(
                consent_type=kind,
                policy_version=None,
                granted=False,
                decided_at=None,
                revoked_at=None,
            )
            for kind in (
                "health_data_processing",
                "mood_data_processing",
                "mood_ai_sharing",
                "third_party_ai",
                "sensitive_image",
                "push_notification",
            )
        ]
        self.deletion_requests: list[AuthContext] = []

    def register(
        self,
        email_value: str,
        password: str,
        birth_year: int,
        privacy_policy_version: str,
        health_data_processing_consent: bool,
        health_data_processing_policy_version: str,
        source: str,
    ) -> UUID:
        self.registered.append(
            {
                "email": email_value,
                "password": password,
                "birth_year": birth_year,
                "privacy_policy_version": privacy_policy_version,
                "health_data_processing_consent": health_data_processing_consent,
                "health_data_processing_policy_version": health_data_processing_policy_version,
                "source": source,
            }
        )
        return uuid4()

    def verify_email(self, raw_token: str, source: str) -> None:
        self.verified.append(raw_token)

    def login(self, email_value: str, password: str, source: str) -> TokenPair:
        if password == "incorrect-password":
            raise Problem(401, "INVALID_CREDENTIALS", "Invalid email or password")
        return TokenPair("access-value-that-is-long", "refresh-value-that-is-long")

    def refresh(self, raw_refresh: str) -> TokenPair:
        if raw_refresh == "expired-value":
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        return TokenPair("rotated-access-value-long", "rotated-refresh-value-long")

    def request_password_reset(self, email_value: str, source: str) -> UUID:
        return uuid4()

    def confirm_password_reset(self, raw_token: str, new_password: str, source: str) -> None:
        return None

    def authenticate_access_token(self, raw_access: str) -> AuthContext:
        if raw_access != "access-value-that-is-long":
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        return AuthContext(uuid4(), uuid4())

    def logout(self, context: AuthContext) -> None:
        self.logged_out.append(context)

    def get_my_profile(self, context: AuthContext) -> PatientProfileData:
        return self.profile

    def patch_my_profile(
        self,
        context: AuthContext,
        profile_version: int,
        changes: dict[str, str | int | None],
    ) -> PatientProfileData:
        if profile_version != self.profile.profile_version:
            raise Problem(409, "RECORD_VERSION_CONFLICT", "Patient profile has changed")
        self.profile_changes.append(changes)
        self.profile = PatientProfileData(
            id=self.profile.id,
            nickname=changes.get("nickname", self.profile.nickname),
            birth_year=changes.get("birth_year", self.profile.birth_year),  # type: ignore[arg-type]
            timezone=changes.get("timezone", self.profile.timezone),  # type: ignore[arg-type]
            profile_version=self.profile.profile_version + (1 if changes else 0),
        )
        return self.profile

    def record_consent(
        self,
        context: AuthContext,
        consent_type: str,
        policy_version: str,
        granted: bool,
    ) -> ConsentDecisionData:
        from datetime import UTC, datetime

        self.consent_decisions.append((consent_type, policy_version, granted))
        return ConsentDecisionData(
            consent_type=consent_type,  # type: ignore[arg-type]
            policy_version=policy_version,
            granted=granted,
            decided_at=datetime.now(UTC),
        )

    def get_my_consents(self, context: AuthContext) -> list[ConsentStatusData]:
        return self.consent_statuses

    def request_account_deletion(self, context: AuthContext) -> UUID:
        self.deletion_requests.append(context)
        return uuid4()


class FakePrivacyService:
    def __init__(self) -> None:
        self.deletion_requests: list[AuthContext] = []

    def request_deletion(self, context: AuthContext) -> tuple[UUID, str]:
        self.deletion_requests.append(context)
        return uuid4(), "receipt-value-with-more-than-forty-characters-0123456789"

    def deletion_status(self, operation_id: UUID, receipt: str) -> dict[str, object]:
        from datetime import UTC, datetime

        return {
            "operation_id": operation_id,
            "status": "pending",
            "requested_at": datetime.now(UTC),
            "due_at": datetime.now(UTC),
            "completed_at": None,
        }

    def create_export_preview(
        self, context: AuthContext, categories: list[str]
    ) -> tuple[UUID, list[str]]:
        return uuid4(), categories

    def confirm_export(self, context: AuthContext, export_id: UUID) -> None:
        return None

    def cancel_export(self, context: AuthContext, export_id: UUID) -> None:
        return None


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(env="test"))
    app.state.auth_service = FakeAuthService()
    app.state.privacy_service = FakePrivacyService()
    return TestClient(app)


def test_register_uses_frozen_request_and_accepted_response(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "patient@example.com",
            "password": "correct-horse-battery",
            "birth_year": 1990,
            "privacy_policy_version": "v1",
            "health_data_processing_consent": True,
            "health_data_processing_policy_version": "health-v1",
        },
    )
    assert response.status_code == 202
    assert set(response.json()) == {"operation_id", "status"}
    assert response.json()["status"] == "accepted"
    UUID(response.json()["operation_id"])
    assert client.app.state.auth_service.registered[0]["birth_year"] == 1990
    assert "nickname" not in client.app.state.auth_service.registered[0]


def test_register_rejects_unfrozen_fields_and_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "patient@example.com",
            "password": "too-short",
            "birth_year": 1990,
            "privacy_policy_version": "v1",
            "health_data_processing_consent": True,
            "health_data_processing_policy_version": "health-v1",
            "phone_number": "+15550000000",
            "nickname": "not allowed at registration",
        },
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "+15550000000" not in str(response.json())
    assert "too-short" not in str(response.json())


def test_email_verification_returns_no_content(client: TestClient) -> None:
    response = client.post("/api/v1/auth/email/verify", json={"token": "t" * 32})
    assert response.status_code == 204
    assert response.content == b""
    assert client.app.state.auth_service.verified == ["t" * 32]


def test_login_and_refresh_use_frozen_token_pair_dto(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "patient@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert login.json() == {
        "access_token": "access-value-that-is-long",
        "refresh_token": "refresh-value-that-is-long",
        "token_type": "Bearer",
        "expires_in": 900,
    }
    refresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "refresh-value-that-is-long"}
    )
    assert refresh.status_code == 200
    assert refresh.json()["refresh_token"] == "rotated-refresh-value-long"

    short_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": "short"})
    assert short_refresh.status_code == 422
    assert short_refresh.json()["code"] == "VALIDATION_ERROR"


def test_logout_requires_bearer_and_revokes_current_context(client: TestClient) -> None:
    missing = client.post("/api/v1/auth/logout")
    assert missing.status_code == 401
    assert missing.json()["code"] == "AUTHENTICATION_REQUIRED"

    response = client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer access-value-that-is-long"}
    )
    assert response.status_code == 204
    assert len(client.app.state.auth_service.logged_out) == 1


def test_invalid_login_does_not_reflect_email_or_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "patient@example.com", "password": "incorrect-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert "patient@example.com" not in response.text
    assert "incorrect-password" not in response.text


def test_openapi_exposes_frozen_auth_operations_and_bearer_logout(client: TestClient) -> None:
    schema = client.app.openapi()
    paths = schema["paths"]
    assert paths["/api/v1/auth/register"]["post"]["operationId"] == "register"
    assert paths["/api/v1/auth/email/verify"]["post"]["operationId"] == "verifyEmail"
    assert paths["/api/v1/auth/login"]["post"]["operationId"] == "login"
    assert paths["/api/v1/auth/refresh"]["post"]["operationId"] == "refreshSession"
    assert paths["/api/v1/auth/logout"]["post"]["operationId"] == "logout"
    logout_security = paths["/api/v1/auth/logout"]["post"]["security"]
    assert logout_security == [{"bearerAuth": []}]
    assert "bearerAuth" in schema["components"]["securitySchemes"]
    register_body = paths["/api/v1/auth/register"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    if "$ref" in register_body:
        register_body = schema["components"]["schemas"]["RegisterRequest"]
    assert register_body["additionalProperties"] is False
    assert "phone_number" not in register_body["properties"]
    assert "nickname" not in register_body["properties"]
    assert "privacy_policy_version" in register_body["required"]
    assert "health_data_processing_consent" in register_body["required"]
    assert register_body["properties"]["health_data_processing_consent"]["const"] is True
    accepted = schema["components"]["schemas"]["AcceptedOperation"]
    assert accepted["additionalProperties"] is False
    assert accepted["properties"]["status"]["const"] == "accepted"
    token_pair = schema["components"]["schemas"]["TokenPairResponse"]
    assert token_pair["additionalProperties"] is False
    assert token_pair["properties"]["access_token"]["minLength"] == 20
    assert token_pair["properties"]["refresh_token"]["minLength"] == 20
    assert (
        paths["/api/v1/auth/password/reset/request"]["post"]["operationId"]
        == "requestPasswordReset"
    )
    assert (
        paths["/api/v1/auth/password/reset/confirm"]["post"]["operationId"]
        == "confirmPasswordReset"
    )
    assert list(paths["/api/v1/auth/register"]["post"]["responses"]["422"]["content"]) == [
        "application/problem+json"
    ]
    assert "503" in paths["/api/v1/auth/register"]["post"]["responses"]
    assert (
        "application/problem+json"
        in paths["/api/v1/auth/logout"]["post"]["responses"]["401"]["content"]
    )
    assert paths["/api/v1/patients/me"]["get"]["operationId"] == "getMyProfile"
    assert paths["/api/v1/patients/me"]["patch"]["operationId"] == "updateMyProfile"
    assert paths["/api/v1/patients/me/consents"]["post"]["operationId"] == "recordConsent"
    assert paths["/api/v1/patients/me/consents"]["get"]["operationId"] == "getMyConsents"
    assert paths["/api/v1/consent-notices"]["get"]["operationId"] == "getConsentNotice"
    assert (
        paths["/api/v1/patients/me/account-deletion"]["post"]["operationId"]
        == "requestAccountDeletion"
    )
    profile_patch = schema["components"]["schemas"]["PatientProfilePatchRequest"]
    assert profile_patch["additionalProperties"] is False
    assert profile_patch["required"] == ["profile_version"]
    assert "profile_version" in profile_patch["properties"]
    consent_input = paths["/api/v1/patients/me/consents"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    if "$ref" in consent_input:
        consent_input = schema["components"]["schemas"][consent_input["$ref"].rsplit("/", 1)[-1]]
    assert "privacy_policy" not in consent_input["properties"]["consent_type"]["enum"]
    for route, method in (
        ("/api/v1/patients/me", "get"),
        ("/api/v1/patients/me", "patch"),
        ("/api/v1/patients/me/consents", "post"),
    ):
        assert "application/problem+json" in paths[route][method]["responses"]["401"]["content"]


def test_profile_routes_require_auth_and_use_optimistic_version(client: TestClient) -> None:
    unauthenticated = client.get("/api/v1/patients/me")
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["content-type"].startswith("application/problem+json")
    assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"

    headers = {"Authorization": "Bearer access-value-that-is-long"}
    current = client.get("/api/v1/patients/me", headers=headers)
    assert current.status_code == 200
    assert current.json()["profile_version"] == 1
    assert "user_id" not in current.json()
    assert "patient_id" not in current.json()

    updated = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "nickname": "Lin"},
    )
    assert updated.status_code == 200
    assert updated.json()["nickname"] == "Lin"
    assert updated.json()["profile_version"] == 2
    assert client.app.state.auth_service.profile_changes[-1] == {"nickname": "Lin"}

    stale = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "nickname": "stale"},
    )
    assert stale.status_code == 409
    assert stale.headers["content-type"].startswith("application/problem+json")
    assert stale.json()["code"] == "RECORD_VERSION_CONFLICT"


def test_profile_patch_null_and_foreign_scope_fields_are_rejected(client: TestClient) -> None:
    headers = {"Authorization": "Bearer access-value-that-is-long"}
    null_birth_year = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "birth_year": None},
    )
    foreign_id = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "patient_id": str(uuid4())},
    )
    null_timezone = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "timezone": None},
    )
    for response in (null_birth_year, null_timezone, foreign_id):
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "VALIDATION_ERROR"


def test_profile_timezone_requires_an_iana_zone(client: TestClient) -> None:
    headers = {"Authorization": "Bearer access-value-that-is-long"}
    invalid = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "timezone": "Mars/Olympus"},
    )
    assert invalid.status_code == 422
    assert invalid.headers["content-type"].startswith("application/problem+json")
    assert invalid.json()["code"] == "VALIDATION_ERROR"
    assert client.app.state.auth_service.profile_changes == []

    valid = client.patch(
        "/api/v1/patients/me",
        headers=headers,
        json={"profile_version": 1, "timezone": "America/New_York"},
    )
    assert valid.status_code == 200
    assert valid.json()["timezone"] == "America/New_York"


def test_consent_decisions_record_version_and_allow_revocation(client: TestClient) -> None:
    headers = {"Authorization": "Bearer access-value-that-is-long"}
    granted = client.post(
        "/api/v1/patients/me/consents",
        headers=headers,
        json={
            "consent_type": "third_party_ai",
            "policy_version": "third_party_ai-v1",
            "granted": True,
        },
    )
    revoked = client.post(
        "/api/v1/patients/me/consents",
        headers=headers,
        json={
            "consent_type": "third_party_ai",
            "policy_version": "third_party_ai-v1",
            "granted": False,
        },
    )
    assert granted.status_code == revoked.status_code == 201
    assert granted.json()["consent_type"] == "third_party_ai"
    assert granted.json()["policy_version"] == "third_party_ai-v1"
    assert granted.json()["granted"] is True
    assert revoked.json()["granted"] is False
    assert "notice_summary_hash" not in granted.json()
    assert client.app.state.auth_service.consent_decisions == [
        ("third_party_ai", "third_party_ai-v1", True),
        ("third_party_ai", "third_party_ai-v1", False),
    ]

    privacy_withdrawal = client.post(
        "/api/v1/patients/me/consents",
        headers=headers,
        json={"consent_type": "privacy_policy", "policy_version": "privacy-v1", "granted": False},
    )
    assert privacy_withdrawal.status_code == 422
    assert privacy_withdrawal.json()["code"] == "VALIDATION_ERROR"


def test_consent_status_is_authenticated_latest_only_and_never_exposes_metadata(
    client: TestClient,
) -> None:
    unauthenticated = client.get("/api/v1/patients/me/consents")
    assert unauthenticated.status_code == 401
    response = client.get(
        "/api/v1/patients/me/consents",
        headers={"Authorization": "Bearer access-value-that-is-long"},
    )
    assert response.status_code == 200
    mood = next(item for item in response.json() if item["consent_type"] == "mood_data_processing")
    assert mood == {
        "consent_type": "mood_data_processing",
        "policy_version": None,
        "granted": False,
        "decided_at": None,
        "revoked_at": None,
    }
    assert all("metadata" not in item and "summary_hash" not in item for item in response.json())

    from datetime import UTC, datetime

    decided_at = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    client.app.state.auth_service.consent_statuses = [
        ConsentStatusData(
            consent_type="mood_data_processing",
            policy_version="test-only-mood-data-v1",
            granted=False,
            decided_at=decided_at,
            revoked_at=decided_at,
        )
    ]
    revoked_response = client.get(
        "/api/v1/patients/me/consents",
        headers={"Authorization": "Bearer access-value-that-is-long"},
    )
    revoked = next(
        item for item in revoked_response.json() if item["consent_type"] == "mood_data_processing"
    )
    assert revoked["granted"] is False
    assert revoked["policy_version"] == "test-only-mood-data-v1"
    assert revoked["revoked_at"] == decided_at.isoformat().replace("+00:00", "Z")


def test_consent_notice_is_authenticated_and_fails_closed_without_matching_config(
    client: TestClient,
) -> None:
    unauthenticated = client.get(
        "/api/v1/consent-notices", params={"consent_type": "mood_data_processing"}
    )
    assert unauthenticated.status_code == 401
    response = client.get(
        "/api/v1/consent-notices",
        params={"consent_type": "mood_data_processing"},
        headers={"Authorization": "Bearer access-value-that-is-long"},
    )
    assert response.status_code == 200
    assert response.json() == {"consent_type": "mood_data_processing", "enabled": False}
    assert (
        client.get(
            "/api/v1/consent-notices",
            params={"consent_type": "unknown"},
            headers={"Authorization": "Bearer access-value-that-is-long"},
        ).status_code
        == 422
    )


def test_consent_notice_returns_only_matching_test_artifact_without_hash(
    client: TestClient,
) -> None:
    settings = client.app.state.settings
    settings.mood_data_processing_policy_version = "test-only-mood-data-v1"
    settings.mood_data_processing_summary_hash = (
        "7d30d978677482a02db144506c80aed867dcc395b82a96a4a1eda90a87c578e4"
    )
    response = client.get(
        "/api/v1/consent-notices",
        params={"consent_type": "mood_data_processing"},
        headers={"Authorization": "Bearer access-value-that-is-long"},
    )
    assert response.status_code == 200
    notice = response.json()
    assert notice["enabled"] is True
    assert notice["policy_version"] == "test-only-mood-data-v1"
    assert "test build" not in notice["summary"].lower()
    assert "开发/自动化" not in notice["summary"]
    assert "summary_sha256" not in notice and "metadata" not in notice


def test_account_deletion_requires_auth_and_returns_operation(client: TestClient) -> None:
    missing = client.post("/api/v1/patients/me/account-deletion")
    assert missing.status_code == 401
    assert missing.json()["code"] == "AUTHENTICATION_REQUIRED"

    response = client.post(
        "/api/v1/patients/me/account-deletion",
        headers={"Authorization": "Bearer access-value-that-is-long"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    UUID(response.json()["operation_id"])
    assert len(client.app.state.privacy_service.deletion_requests) == 1
    assert len(response.json()["receipt"]) >= 40


def test_register_requires_explicit_health_data_consent(client: TestClient) -> None:
    base = {
        "email": "patient@example.com",
        "password": "correct-horse-battery",
        "birth_year": 1990,
        "privacy_policy_version": "v1",
    }
    missing = client.post("/api/v1/auth/register", json=base)
    declined = client.post(
        "/api/v1/auth/register",
        json={
            **base,
            "health_data_processing_consent": False,
            "health_data_processing_policy_version": "health-v1",
        },
    )
    assert missing.status_code == declined.status_code == 422
    assert not client.app.state.auth_service.registered


def test_openapi_account_deletion_requires_authenticated_operation() -> None:
    app = create_app(Settings(env="test"))
    schema = app.openapi()
    deletion = schema["paths"]["/api/v1/patients/me/account-deletion"]["post"]
    assert deletion["operationId"] == "requestAccountDeletion"
    assert deletion["security"] == [{"bearerAuth": []}]
    assert "202" in deletion["responses"] and "401" in deletion["responses"]
    assert "404" in deletion["responses"] and "500" in deletion["responses"]
    assert set(deletion["responses"]["202"]["content"]["application/json"]["examples"]) == {
        "firstAcceptance",
        "idempotentRetry",
    }
    status = schema["paths"]["/api/v1/privacy/deletion-operations/{operation_id}/status"]["post"]
    assert status["operationId"] == "getPrivacyDeletionStatus"
    assert {"200", "404", "422", "429", "503"}.issubset(status["responses"])
    assert {"pending", "processing", "overdue", "deadLetter", "completed"}.issubset(
        status["responses"]["200"]["content"]["application/json"]["examples"]
    )
    deletion_status = schema["components"]["schemas"]["DeleteStatus"]
    assert deletion_status["properties"]["status"]["enum"] == [
        "pending",
        "processing",
        "overdue",
        "dead_letter",
        "completed",
    ]
    assert "/api/v1/privacy/exports" in schema["paths"]
    assert "/api/v1/privacy/exports/download" in schema["paths"]
    assert "X-Export-Capability" in str(schema["paths"]["/api/v1/privacy/exports/download"])


def test_password_reset_routes_follow_frozen_contract(client: TestClient) -> None:
    request = client.post(
        "/api/v1/auth/password/reset/request", json={"email": "patient@example.com"}
    )
    assert request.status_code == 202
    assert request.json()["status"] == "accepted"
    confirm = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "t" * 32, "new_password": "new-correct-horse"},
    )
    assert confirm.status_code == 204


def test_frozen_openapi_auth_shapes_match_runtime_constraints() -> None:
    contract_path = Path(__file__).resolve().parents[2] / "contracts/openapi/gutcare-v1.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime = create_app(Settings(env="test")).openapi()
    static_register_responses = contract["paths"]["/auth/register"]["post"]["responses"]
    runtime_register_responses = runtime["paths"]["/api/v1/auth/register"]["post"]["responses"]
    assert (
        set(static_register_responses)
        == set(runtime_register_responses)
        == {
            "202",
            "422",
            "429",
            "500",
            "503",
        }
    )
    assert "401" not in static_register_responses
    schemas = contract["components"]["schemas"]
    accepted = schemas["AcceptedOperation"]
    assert accepted["additionalProperties"] is False
    assert accepted["properties"]["status"] == {"const": "accepted"}
    token_pair = schemas["TokenPair"]
    assert token_pair["additionalProperties"] is False
    assert token_pair["properties"]["access_token"]["minLength"] == 20
    assert token_pair["properties"]["refresh_token"]["minLength"] == 20
    for path, field in (
        ("/auth/email/verify", "token"),
        ("/auth/refresh", "refresh_token"),
        ("/auth/password/reset/confirm", "token"),
    ):
        body = contract["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        assert body["additionalProperties"] is False
        assert body["properties"][field]["minLength"] == 20

    deletion_path = "/patients/me/account-deletion"
    status_path = "/privacy/deletion-operations/{operation_id}/status"
    for path, method, operation_id in (
        (deletion_path, "post", "requestAccountDeletion"),
        (status_path, "post", "getPrivacyDeletionStatus"),
    ):
        static_operation = contract["paths"][path][method]
        runtime_operation = runtime["paths"][f"/api/v1{path}"][method]
        assert static_operation["operationId"] == runtime_operation["operationId"] == operation_id
        assert set(static_operation["responses"]) == set(runtime_operation["responses"])
    assert (
        contract["components"]["schemas"]["PrivacyDeletionStatus"]["properties"]["status"]["enum"]
        == runtime["components"]["schemas"]["DeleteStatus"]["properties"]["status"]["enum"]
    )
