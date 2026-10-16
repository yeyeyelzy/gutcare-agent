"""Unit tests for account lookup, email encryption, and token digest helpers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Lock, local
from uuid import uuid4

import jwt
import pytest
from sqlalchemy.orm import sessionmaker

from gutcare.auth.models import Base, PatientConsent, PatientProfile, RefreshSession, UserAccount
from gutcare.auth.security import (
    decrypt_email,
    email_lookup_hash,
    encrypt_email,
    new_opaque_token,
    normalize_email,
    token_digest,
    utc_now,
)
from gutcare.auth.service import AuthService, password_hasher
from gutcare.config import Settings
from gutcare.shared.errors import Problem

_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"


def test_email_ciphertext_is_authenticated_and_randomized() -> None:
    first = encrypt_email("patient@example.invalid", _KEY)
    second = encrypt_email("patient@example.invalid", _KEY)
    assert first != second
    assert decrypt_email(first, _KEY) == "patient@example.invalid"


def test_email_lookup_uses_peppered_stable_digest() -> None:
    address = normalize_email("Patient@EXAMPLE.COM")
    assert address == "Patient@example.com"
    assert address == normalize_email("Patient@example.com")
    assert address != normalize_email("patient@example.com")
    assert email_lookup_hash(address, "pepper-one") == email_lookup_hash(address, "pepper-one")
    assert email_lookup_hash(address, "pepper-one") != email_lookup_hash(address, "pepper-two")


def test_opaque_token_is_high_entropy_and_only_digest_is_persisted() -> None:
    token = new_opaque_token()
    assert len(token) >= 64
    assert token_digest(token) != token
    assert token_digest(token) == token_digest(token)


def test_frozen_hash_and_database_types_are_preserved() -> None:
    account = Base.metadata.tables["iam.user_account"]
    assert account.c.email_lookup_hash.type.__class__.__name__ == "CHAR"
    assert account.c.password_hash.type.length == 255
    assert str(account.c.id.server_default.arg) == "uuidv7()"
    assert UserAccount.__table__.schema == "iam"
    assert Base.metadata.tables["health.patient_profile"].c.birth_year.nullable is False
    family_fk = next(
        fk
        for fk in RefreshSession.__table__.c.family_id.foreign_keys
        if fk.name == "fk_refresh_session_family_root"
    )
    assert family_fk.column is RefreshSession.__table__.c.id
    assert family_fk.deferrable is True
    assert family_fk.initially == "DEFERRED"


def test_argon2id_hash_and_jwt_claims_follow_auth_baseline() -> None:
    password_hash = password_hasher.hash("sample-password-123")
    assert password_hash.startswith("$argon2id$")
    assert password_hasher.verify("sample-password-123", password_hash)
    assert not password_hasher.verify("different-password-123", password_hash)

    signing_key = "a" * 32
    settings = Settings(
        env="test",
        jwt_signing_key=signing_key,
        jwt_issuer="gutcare-business-api",
        jwt_audience="gutcare-mobile-app",
    )
    service = AuthService(settings, sessionmaker())
    user_id = uuid4()
    session_id = uuid4()
    encoded = service._new_access_token(user_id, session_id)
    claims = jwt.decode(
        encoded,
        signing_key,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert int(claims["exp"] - claims["iat"]) == 15 * 60


class _FakeTransaction:
    def __init__(self, database: "_FakeAuthDatabase") -> None:
        self.database = database

    def __enter__(self) -> "_FakeAuthDatabase":
        self.database.held_family_locks.values = []
        return self.database

    def __exit__(self, *args: object) -> None:
        for family_lock in reversed(self.database.held_family_locks.values):
            family_lock.release()
        return None


class _FakeAuthDatabase:
    def __init__(self, account: UserAccount | None, sessions: list[RefreshSession]) -> None:
        self.account = account
        self.sessions = sessions
        self.added: list[object] = []
        self._lock_catalog_lock = Lock()
        self._family_locks: dict[object, Lock] = {}
        self.held_family_locks = local()
        self.root_lock_acquired = Event()
        self.second_root_lock_attempting = Event()
        self.allow_first_root_holder = Event()
        self.pause_first_root_holder = True
        self.pause_after_session_add = False
        self.session_added = Event()
        self.allow_commit = Event()
        self._root_lock_count = 0
        self._root_lock_count_lock = Lock()

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def scalar(self, query: object) -> object:
        entity = query.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        if entity is RefreshSession:
            params = query.compile().params  # type: ignore[attr-defined]
            digest = params.get("token_hash_1")
            if digest is not None:
                return next((item for item in self.sessions if item.token_hash == digest), None)
            session_id = params.get("id_1")
            if session_id is not None and query._for_update_arg is not None:  # type: ignore[attr-defined]
                family_id = session_id
                with self._lock_catalog_lock:
                    family_lock = self._family_locks.setdefault(family_id, Lock())
                with self._root_lock_count_lock:
                    self._root_lock_count += 1
                    lock_number = self._root_lock_count
                if lock_number == 2:
                    self.second_root_lock_attempting.set()
                family_lock.acquire()
                self.held_family_locks.values.append(family_lock)
                if lock_number == 1 and self.pause_first_root_holder:
                    self.root_lock_acquired.set()
                    self.allow_first_root_holder.wait(timeout=5)
                return next((item for item in self.sessions if item.id == family_id), None)
            if session_id is not None:
                return next((item for item in self.sessions if item.id == session_id), None)
            return None
        return self.account

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, RefreshSession):
            self.sessions.append(value)
            if self.pause_after_session_add:
                self.session_added.set()
                self.allow_commit.wait(timeout=5)

    def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()  # type: ignore[attr-defined]

    def get(self, model: type[RefreshSession], session_id: object) -> RefreshSession | None:
        return next((item for item in self.sessions if item.id == session_id), None)

    def execute(self, statement: object, parameters: dict[str, object]) -> None:
        if "UPDATE iam.refresh_session" in str(statement):
            family_id = parameters["family_id"]
            now = parameters["now"]
            for item in self.sessions:
                if item.family_id == family_id and item.revoked_at is None:
                    item.revoked_at = now  # type: ignore[assignment]


def test_refresh_rotation_lineage_and_replay_revokes_entire_family() -> None:
    user_id = uuid4()
    original_token = new_opaque_token()
    original = RefreshSession(
        id=uuid4(),
        user_id=user_id,
        family_id=uuid4(),
        token_hash=token_digest(original_token),
        expires_at=utc_now() + timedelta(days=2),
    )
    original.family_id = original.id
    family_id = original.id
    account = UserAccount(id=user_id, status="active")
    database = _FakeAuthDatabase(account, [original])

    class Factory:
        def begin(self) -> _FakeTransaction:
            return database.begin()

    class NoopLimiter:
        def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
            return None

    service = AuthService(
        Settings(env="test", jwt_signing_key="s" * 32),
        Factory(),  # type: ignore[arg-type]
        rate_limiter=NoopLimiter(),
    )
    first_rotated = service.refresh(original_token)
    first_successor = database.sessions[-1]
    assert original.replaced_by_session_id == first_successor.id
    assert first_successor.parent_session_id == original.id
    assert first_successor.family_id == family_id

    second_rotated = service.refresh(first_rotated.refresh_token)
    assert second_rotated.refresh_token != first_rotated.refresh_token
    second_successor = database.sessions[-1]
    assert second_successor.parent_session_id == first_successor.id

    with pytest.raises(Problem) as replay:
        service.refresh(original_token)
    assert replay.value.status == 401
    assert all(item.revoked_at is not None for item in database.sessions)


def test_concurrent_refresh_replay_invalidates_winning_successor() -> None:
    user_id = uuid4()
    original_token = new_opaque_token()
    original = RefreshSession(
        id=uuid4(),
        user_id=user_id,
        family_id=uuid4(),
        token_hash=token_digest(original_token),
        expires_at=utc_now() + timedelta(days=2),
    )
    original.family_id = original.id
    database = _FakeAuthDatabase(UserAccount(id=user_id, status="active"), [original])

    class Factory:
        def begin(self) -> _FakeTransaction:
            return database.begin()

    class NoopLimiter:
        def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
            return None

    service = AuthService(
        Settings(env="test", jwt_signing_key="s" * 32),
        Factory(),  # type: ignore[arg-type]
        rate_limiter=NoopLimiter(),
    )

    def rotate() -> str:
        try:
            return service.refresh(original_token).refresh_token
        except Problem as error:
            return f"rejected:{error.code}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(rotate)
        assert database.root_lock_acquired.wait(timeout=5)
        second = executor.submit(rotate)
        assert database.second_root_lock_attempting.wait(timeout=5)
        database.allow_first_root_holder.set()
        first_result = first.result(timeout=5)
        second_result = second.result(timeout=5)

    assert not first_result.startswith("rejected")
    assert second_result.startswith("rejected:")
    assert all(item.revoked_at is not None for item in database.sessions)


def test_replay_of_s0_waits_for_s1_rotation_commit_then_revokes_s2() -> None:
    user_id = uuid4()
    s0_token = new_opaque_token()
    s0 = RefreshSession(
        id=uuid4(),
        user_id=user_id,
        family_id=uuid4(),
        token_hash=token_digest(s0_token),
        expires_at=utc_now() + timedelta(days=2),
    )
    s0.family_id = s0.id
    database = _FakeAuthDatabase(UserAccount(id=user_id, status="active"), [s0])

    class Factory:
        def begin(self) -> _FakeTransaction:
            return database.begin()

    class NoopLimiter:
        def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
            return None

    service = AuthService(
        Settings(env="test", jwt_signing_key="s" * 32),
        Factory(),  # type: ignore[arg-type]
        rate_limiter=NoopLimiter(),
    )

    # Establish S0 -> S1 before racing. Reset lock coordination so the upcoming
    # refresh of S1 is the first holder and the replay of S0 is the waiter.
    s1_pair = service.refresh(s0_token)
    s1 = database.sessions[-1]
    assert s0.revoked_at is not None
    assert s0.replaced_by_session_id == s1.id
    database._root_lock_count = 0
    database.root_lock_acquired.clear()
    database.second_root_lock_attempting.clear()
    database.allow_first_root_holder.set()
    database.pause_first_root_holder = False
    database.pause_after_session_add = True
    database.allow_commit.clear()

    def refresh_s1() -> str:
        return service.refresh(s1_pair.refresh_token).refresh_token

    def replay_s0() -> str:
        try:
            service.refresh(s0_token)
        except Problem as error:
            return f"rejected:{error.code}"
        return "unexpected-success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        thread_a = executor.submit(refresh_s1)
        assert database.session_added.wait(timeout=5)  # S2 exists, A still owns family lock.
        thread_b = executor.submit(replay_s0)
        assert database.second_root_lock_attempting.wait(timeout=5)
        assert not thread_b.done()  # It is blocked on the same family root lock.
        database.allow_commit.set()
        s2_token = thread_a.result(timeout=5)
        replay_result = thread_b.result(timeout=5)

    database.pause_after_session_add = False
    s2 = database.sessions[-1]
    assert s2.token_hash == token_digest(s2_token)
    assert s2.parent_session_id == s1.id
    assert replay_result == "rejected:AUTHENTICATION_REQUIRED"
    assert s1.revoked_at is not None
    assert s2.revoked_at is not None
    with pytest.raises(Problem) as unusable_successor:
        service.refresh(s2_token)
    assert unusable_successor.value.status == 401


def test_unverified_and_unknown_accounts_have_identical_login_error() -> None:
    email = normalize_email("patient@example.com")
    pepper = "p" * 32
    pending = UserAccount(
        id=uuid4(),
        email_lookup_hash=email_lookup_hash(email, pepper),
        status="pending_verification",
        password_hash=password_hasher.hash("correct-horse-battery"),
        failed_login_count=0,
    )

    class NoopLimiter:
        def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
            return None

    def rejected_login(account: UserAccount | None) -> Problem:
        database = _FakeAuthDatabase(account, [])

        class Factory:
            def begin(self) -> _FakeTransaction:
                return database.begin()

        service = AuthService(
            Settings(env="test", email_lookup_pepper=pepper),
            Factory(),  # type: ignore[arg-type]
            rate_limiter=NoopLimiter(),
        )
        with pytest.raises(Problem) as error:
            service.login(email, "incorrect-password", "192.0.2.1")
        return error.value

    unknown_error = rejected_login(None)
    pending_error = rejected_login(pending)
    assert (unknown_error.status, unknown_error.code, unknown_error.title) == (
        pending_error.status,
        pending_error.code,
        pending_error.title,
    )
    assert (unknown_error.status, unknown_error.code) == (401, "INVALID_CREDENTIALS")


def test_registration_records_distinct_privacy_and_health_data_consents() -> None:
    database = _FakeAuthDatabase(None, [])

    class Factory:
        def begin(self) -> _FakeTransaction:
            return database.begin()

    class NoopLimiter:
        def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
            return None

    class EmailSink:
        def send_verification(self, recipient: str, token: str) -> None:
            assert recipient == "patient@example.com"
            assert token

        def send_password_reset(self, recipient: str, token: str) -> None:
            raise AssertionError("unexpected password reset")

    privacy_hash = "1" * 64
    health_hash = "2" * 64
    service = AuthService(
        Settings(
            env="test",
            email_lookup_pepper="p" * 32,
            email_encryption_key=_KEY,
            privacy_policy_summary_hash=privacy_hash,
            health_data_processing_summary_hash=health_hash,
            privacy_policy_version="privacy-v1",
            health_data_processing_policy_version="health-v2",
        ),
        Factory(),  # type: ignore[arg-type]
        email_provider=EmailSink(),
        rate_limiter=NoopLimiter(),
    )
    service.register(
        "patient@example.com",
        "correct-horse-battery",
        1990,
        "privacy-v1",
        True,
        "health-v2",
        "192.0.2.1",
    )

    profile = next(item for item in database.added if isinstance(item, PatientProfile))
    consent_records = [item for item in database.added if isinstance(item, PatientConsent)]
    assert profile.birth_year == 1990
    assert profile.nickname is None
    assert {item.consent_type for item in consent_records} == {
        "privacy_policy",
        "health_data_processing",
    }
    by_type = {item.consent_type: item for item in consent_records}
    assert by_type["privacy_policy"].document_version == "privacy-v1"
    assert by_type["privacy_policy"].metadata_json["notice_summary_hash"] == privacy_hash
    assert by_type["health_data_processing"].document_version == "health-v2"
    assert by_type["health_data_processing"].metadata_json["notice_summary_hash"] == health_hash
