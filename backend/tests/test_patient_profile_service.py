"""Patient profile and consent scoping tests without a PostgreSQL replacement claim."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from gutcare.auth.models import (
    AccountDeletionRequest,
    PatientConsent,
    PatientProfile,
    RefreshSession,
    UserAccount,
)
from gutcare.auth.security import new_opaque_token, token_digest, utc_now
from gutcare.auth.service import AuthContext, AuthService
from gutcare.config import Settings
from gutcare.shared.errors import Problem


class _Transaction:
    def __init__(self, database: "_ProfileDatabase") -> None:
        self.database = database

    def __enter__(self) -> "_ProfileDatabase":
        return self.database

    def __exit__(self, *args: object) -> None:
        return None


class _ProfileDatabase:
    def __init__(self, profiles: list[PatientProfile]) -> None:
        self.profiles = profiles
        self.consents: list[PatientConsent] = []
        self.rls_context: dict[str, str] = {}

    def begin(self) -> _Transaction:
        return _Transaction(self)

    def scalar(self, query: Any) -> PatientProfile | None:
        entity = query.column_descriptions[0]["entity"]
        if entity is PatientConsent:
            parameters = query.compile().params
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
        if entity is not PatientProfile:
            raise AssertionError(f"Unexpected query entity: {entity}")
        parameters = query.compile().params
        user_id = parameters.get("user_id_1")
        if user_id is not None:
            return next((item for item in self.profiles if item.user_id == user_id), None)
        profile_id = parameters.get("id_1")
        return next((item for item in self.profiles if item.id == profile_id), None)

    def scalars(self, query: Any) -> list[object]:
        del query
        return []

    def execute(self, statement: object, parameters: dict[str, object]) -> None:
        if "set_config" in str(statement):
            key = "app.user_id" if "user_id" in str(statement) else "app.patient_id"
            self.rls_context[key] = str(parameters[key.rsplit(".", 1)[-1]])

    def add(self, value: object) -> None:
        if isinstance(value, PatientConsent):
            self.consents.append(value)
        else:
            raise AssertionError(f"Unexpected insert: {type(value)}")

    def flush(self) -> None:
        return None


def _profile(user_id: UUID, birth_year: int) -> PatientProfile:
    return PatientProfile(
        id=uuid4(),
        user_id=user_id,
        nickname=None,
        birth_year=birth_year,
        timezone="Asia/Shanghai",
        profile_version=1,
    )


def _service(database: _ProfileDatabase) -> AuthService:
    class Factory:
        def begin(self) -> _Transaction:
            return database.begin()

    hashes = [f"{number:x}" * 64 for number in range(1, 6)]
    artifact = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/consent/consent-notices.json").read_text(
            encoding="utf-8"
        )
    )
    config = artifact["backend_config"]
    return AuthService(
        Settings(
            env="test",
            consent_notices_path=Path(__file__).resolve().parents[2]
            / "contracts/consent/consent-notices.json",
            privacy_policy_summary_hash=hashes[0],
            health_data_processing_summary_hash=config["HEALTH_DATA_PROCESSING_SUMMARY_HASH"],
            sensitive_image_summary_hash=hashes[2],
            third_party_ai_summary_hash=config["THIRD_PARTY_AI_SUMMARY_HASH"],
            push_notification_summary_hash=hashes[4],
            privacy_policy_version="privacy-v1",
            health_data_processing_policy_version=config["HEALTH_DATA_PROCESSING_POLICY_VERSION"],
            sensitive_image_policy_version="sensitive_image-v1",
            third_party_ai_policy_version=config["THIRD_PARTY_AI_POLICY_VERSION"],
            push_notification_policy_version="push_notification-v1",
        ),
        Factory(),  # type: ignore[arg-type]
    )


def test_profile_reads_and_patches_are_scoped_to_authenticated_user() -> None:
    user_a, user_b = uuid4(), uuid4()
    patient_a, patient_b = _profile(user_a, 1990), _profile(user_b, 1980)
    database = _ProfileDatabase([patient_a, patient_b])
    service = _service(database)

    profile_a = service.get_my_profile(AuthContext(user_a, uuid4()))
    assert profile_a.id == patient_a.id
    assert profile_a.birth_year == 1990
    assert database.rls_context == {
        "app.user_id": str(user_a),
        "app.patient_id": str(patient_a.id),
    }

    updated = service.patch_my_profile(
        AuthContext(user_a, uuid4()), profile_version=1, changes={"nickname": "A"}
    )
    assert updated.nickname == "A"
    assert updated.birth_year == 1990
    assert updated.profile_version == 2
    assert patient_b.nickname is None
    assert patient_b.profile_version == 1

    unchanged = service.patch_my_profile(
        AuthContext(user_a, uuid4()), profile_version=2, changes={}
    )
    assert unchanged.profile_version == 2

    with pytest.raises(Problem) as stale:
        service.patch_my_profile(
            AuthContext(user_a, uuid4()), profile_version=1, changes={"nickname": "stale"}
        )
    assert (stale.value.status, stale.value.code) == (409, "RECORD_VERSION_CONFLICT")
    assert patient_a.nickname == "A"

    with pytest.raises(Problem) as invalid_timezone:
        service.patch_my_profile(
            AuthContext(user_a, uuid4()),
            profile_version=2,
            changes={"timezone": "Mars/Olympus"},
        )
    assert (invalid_timezone.value.status, invalid_timezone.value.code) == (
        422,
        "VALIDATION_ERROR",
    )
    assert patient_a.timezone == "Asia/Shanghai"

    with pytest.raises(Problem) as null_timezone:
        service.patch_my_profile(
            AuthContext(user_a, uuid4()), profile_version=2, changes={"timezone": None}
        )
    assert (null_timezone.value.status, null_timezone.value.code) == (422, "VALIDATION_ERROR")


def test_consent_history_keeps_each_type_version_hash_and_revocation() -> None:
    user_id = uuid4()
    profile = _profile(user_id, 1990)
    database = _ProfileDatabase([profile])
    service = _service(database)
    context = AuthContext(user_id, uuid4())

    version = "test-only-third-party-ai-v1"
    first = service.record_consent(context, "third_party_ai", version, True)
    second = service.record_consent(context, "third_party_ai", version, False)

    assert first.granted is True
    assert second.granted is False
    assert first.decided_at <= second.decided_at
    assert len(database.consents) == 2
    grant, revoke = database.consents
    assert grant.patient_id == revoke.patient_id == profile.id
    assert grant.document_version == revoke.document_version == version
    assert grant.consent_type == revoke.consent_type == "third_party_ai"
    assert grant.granted is True and grant.revoked_at is None
    assert revoke.granted is False and revoke.revoked_at == revoke.decided_at
    assert grant.metadata_json == {
        "channel": "mobile_app",
        "notice_summary_hash": "37ae67bc63b6571098aeda40b399ba03ae65270d7aaa451484d06279cdcaa95b",
    }
    assert revoke.metadata_json == grant.metadata_json


def test_withdrawal_uses_existing_notice_hash_without_current_notice_configuration() -> None:
    user_id = uuid4()
    profile = _profile(user_id, 1990)
    database = _ProfileDatabase([profile])
    service = _service(database)
    context = AuthContext(user_id, uuid4())
    service.record_consent(context, "third_party_ai", "test-only-third-party-ai-v1", True)

    service._consent_summary_hash = lambda *_args: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("withdrawal must not require a current notice")
    )
    revoked = service.record_consent(
        context, "third_party_ai", "test-only-third-party-ai-v1", False
    )

    assert revoked.granted is False
    assert database.consents[-1].metadata_json == database.consents[0].metadata_json


def test_withdrawal_requires_an_active_decision_and_matching_policy_version() -> None:
    user_id = uuid4()
    profile = _profile(user_id, 1990)
    database = _ProfileDatabase([profile])
    service = _service(database)
    context = AuthContext(user_id, uuid4())

    with pytest.raises(Problem) as missing:
        service.record_consent(context, "third_party_ai", "test-only-third-party-ai-v1", False)
    assert (missing.value.status, missing.value.code) == (409, "CONSENT_NOT_ACTIVE")

    service.record_consent(context, "third_party_ai", "test-only-third-party-ai-v1", True)
    with pytest.raises(Problem) as stale:
        service.record_consent(context, "third_party_ai", "stale-version", False)
    assert (stale.value.status, stale.value.code) == (422, "VALIDATION_ERROR")


def test_each_consent_type_uses_its_own_server_notice_hash() -> None:
    user_id = uuid4()
    profile = _profile(user_id, 1990)
    database = _ProfileDatabase([profile])
    service = _service(database)
    context = AuthContext(user_id, uuid4())
    expected_hashes = {
        "health_data_processing": (
            "c3c38f369746498cab3b6e9c96bfda09c42230e44e257d56dc47c972e5139be1"
        ),
        "sensitive_image": "3" * 64,
        "third_party_ai": "37ae67bc63b6571098aeda40b399ba03ae65270d7aaa451484d06279cdcaa95b",
        "push_notification": "5" * 64,
    }

    for consent_type in expected_hashes:
        version = {
            "health_data_processing": "test-only-health-v1",
            "third_party_ai": "test-only-third-party-ai-v1",
        }.get(consent_type, f"{consent_type}-v1")
        service.record_consent(context, consent_type, version, True)  # type: ignore[arg-type]

    assert [item.metadata_json["notice_summary_hash"] for item in database.consents] == list(
        expected_hashes.values()
    )
    assert len({item.metadata_json["notice_summary_hash"] for item in database.consents}) == 4


def test_consent_versions_must_match_server_bound_notice_hash() -> None:
    user_id = uuid4()
    profile = _profile(user_id, 1990)
    database = _ProfileDatabase([profile])
    service = _service(database)
    context = AuthContext(user_id, uuid4())

    with pytest.raises(Problem) as unsupported:
        service.record_consent(context, "health_data_processing", "attacker-selected-v9", True)
    assert (unsupported.value.status, unsupported.value.code) == (422, "VALIDATION_ERROR")
    with pytest.raises(Problem) as privacy:
        service.record_consent(context, "privacy_policy", "privacy-v1", False)
    assert (privacy.value.status, privacy.value.code) == (422, "VALIDATION_ERROR")
    assert database.consents == []

    for privacy_version, health_version in (
        ("unconfigured-privacy", "health_data_processing-v1"),
        ("privacy-v1", "unconfigured-health"),
    ):
        with pytest.raises(Problem) as unconfigured:
            service.register(
                "patient@example.com",
                "correct-horse-battery",
                1990,
                privacy_version,
                True,
                health_version,
                "192.0.2.1",
            )
        assert (unconfigured.value.status, unconfigured.value.code) == (422, "VALIDATION_ERROR")
    assert database.consents == []


class _DeletionDatabase:
    def __init__(
        self,
        account: UserAccount,
        refresh_sessions: list[RefreshSession],
    ) -> None:
        self.account = account
        self.refresh_sessions = refresh_sessions
        self.deletion: AccountDeletionRequest | None = None

    def begin(self) -> _Transaction:
        return _Transaction(self)  # type: ignore[arg-type]

    def __call__(self) -> "_DeletionDatabase":
        return self

    def __enter__(self) -> "_DeletionDatabase":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalar(self, query: Any) -> object:
        entity = query.column_descriptions[0]["entity"]
        params = query.compile().params
        if entity is AccountDeletionRequest:
            if self.deletion is not None and self.deletion.user_id == params.get("user_id_1"):
                return self.deletion
            return None
        if entity is UserAccount:
            return self.account if self.account.id == params.get("id_1") else None
        if entity is PatientProfile:
            return None
        if entity is PatientProfile:
            return None
        if entity is RefreshSession:
            session_id = params.get("id_1")
            session = next((item for item in self.refresh_sessions if item.id == session_id), None)
            if (
                session is not None
                and session.revoked_at is None
                and session.expires_at > utc_now()
            ):
                return session
            return None
        raise AssertionError(f"Unexpected query entity: {entity}")

    def execute(self, statement: object, parameters: dict[str, object]) -> None:
        if "analysis_task" in str(statement) or "pg_advisory_xact_lock" in str(statement):
            return
        if "UPDATE iam.refresh_session" in str(statement):
            now = parameters["now"]
            for session in self.refresh_sessions:
                if session.user_id == parameters["user_id"] and session.revoked_at is None:
                    session.revoked_at = now  # type: ignore[assignment]

    def add(self, value: object) -> None:
        assert isinstance(value, AccountDeletionRequest)
        self.deletion = value

    def flush(self) -> None:
        if self.deletion is not None and self.deletion.id is None:
            self.deletion.id = uuid4()

    def get(self, model: type[UserAccount], user_id: object) -> UserAccount | None:
        return self.account if self.account.id == user_id else None


def test_account_deletion_freezes_account_revokes_sessions_and_is_domain_idempotent() -> None:
    user_id = uuid4()
    account = UserAccount(id=user_id, status="active")
    refresh_sessions = [
        RefreshSession(
            id=uuid4(),
            family_id=uuid4(),
            user_id=user_id,
            token_hash=token_digest(new_opaque_token()),
            expires_at=utc_now() + timedelta(days=3),
        )
        for _ in range(2)
    ]
    for session in refresh_sessions:
        session.family_id = session.id
    database = _DeletionDatabase(account, refresh_sessions)
    signing_key = "s" * 32
    service = AuthService(
        Settings(env="test", jwt_signing_key=signing_key),
        database,  # type: ignore[arg-type]
    )
    context = AuthContext(user_id, refresh_sessions[0].id)

    operation_id = service.request_account_deletion(context)
    repeated_operation_id = service.request_account_deletion(context)

    assert operation_id == repeated_operation_id
    assert database.deletion is not None
    assert database.deletion.id == operation_id
    assert database.deletion.status == "pending"
    assert database.deletion.user_id == user_id
    assert account.status == "deactivated"
    assert all(session.revoked_at is not None for session in refresh_sessions)
    with pytest.raises(Problem) as frozen:
        service.authenticate_access_token(service._new_access_token(user_id, context.session_id))
    assert (frozen.value.status, frozen.value.code) == (401, "AUTHENTICATION_REQUIRED")


def test_profile_missing_for_authenticated_user_is_not_disclosed_as_other_profile() -> None:
    database = _ProfileDatabase([_profile(uuid4(), 1990)])
    service = _service(database)
    with pytest.raises(Problem) as missing:
        service.get_my_profile(AuthContext(uuid4(), uuid4()))
    assert (missing.value.status, missing.value.code) == (404, "RESOURCE_NOT_FOUND")


class _IdentityMapTransaction(_Transaction):
    def __enter__(self) -> "_IdentityMapProfileDatabase":
        self.database.identity_map = {}
        return self.database


class _IdentityMapProfileDatabase(_ProfileDatabase):
    def __init__(self, profiles: list[PatientProfile]) -> None:
        super().__init__(profiles)
        self.identity_map: dict[UUID, PatientProfile] = {}
        self.external_update_pending = True

    def begin(self) -> _IdentityMapTransaction:
        return _IdentityMapTransaction(self)  # type: ignore[arg-type]

    @staticmethod
    def _copy_fields(source: PatientProfile, target: PatientProfile) -> None:
        for field in (
            "user_id",
            "nickname",
            "birth_year",
            "timezone",
            "profile_version",
            "updated_at",
            "deleted_at",
        ):
            setattr(target, field, getattr(source, field))

    def scalar(self, query: Any) -> PatientProfile | None:
        parameters = query.compile().params
        user_id = parameters.get("user_id_1")
        if user_id is not None:
            persisted = next((item for item in self.profiles if item.user_id == user_id), None)
            if persisted is None:
                return None
            cached = PatientProfile(
                id=persisted.id,
                user_id=persisted.user_id,
                nickname=persisted.nickname,
                birth_year=persisted.birth_year,
                timezone=persisted.timezone,
                profile_version=persisted.profile_version,
                updated_at=persisted.updated_at,
                deleted_at=persisted.deleted_at,
            )
            self.identity_map[cached.id] = cached
            return cached

        profile_id = parameters.get("id_1")
        persisted = next((item for item in self.profiles if item.id == profile_id), None)
        if persisted is None:
            return None
        cached = self.identity_map[persisted.id]
        if self.external_update_pending:
            # Simulate another committed transaction after the scope lookup but
            # before this SELECT FOR UPDATE refreshes the already-cached entity.
            persisted.nickname = "external"
            persisted.profile_version = 2
            persisted.updated_at = utc_now()
            self.external_update_pending = False
        if query._execution_options.get("populate_existing"):
            self._copy_fields(persisted, cached)
        return cached

    def flush(self) -> None:
        for cached in self.identity_map.values():
            persisted = next(item for item in self.profiles if item.id == cached.id)
            self._copy_fields(cached, persisted)


def test_locked_profile_query_refreshes_identity_map_after_external_commit() -> None:
    user_id = uuid4()
    persisted = _profile(user_id, 1990)
    database = _IdentityMapProfileDatabase([persisted])
    service = _service(database)

    updated = service.patch_my_profile(
        AuthContext(user_id, uuid4()),
        profile_version=2,
        changes={"timezone": "Asia/Tokyo"},
    )

    assert updated.profile_version == 3
    assert updated.nickname == "external"
    assert updated.timezone == "Asia/Tokyo"
    assert persisted.profile_version == 3
