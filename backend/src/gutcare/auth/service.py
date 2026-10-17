"""Email/password account flows backed by the PostgreSQL business schema."""

import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from pwdlib import PasswordHash
from redis import Redis
from sqlalchemy import desc, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from gutcare.analysis.models import AnalysisTask
from gutcare.auth.consent_notices import SUPPORTED_NOTICE_TYPES, resolve_current_consent_notice
from gutcare.auth.models import (
    AccountDeletionRequest,
    EmailVerificationToken,
    PatientConsent,
    PatientProfile,
    RefreshSession,
    UserAccount,
)
from gutcare.auth.security import (
    decrypt_email,
    email_lookup_hash,
    encrypt_email,
    new_opaque_token,
    normalize_email,
    token_digest,
    utc_now,
)
from gutcare.config import Settings
from gutcare.files.models import MedicalFieldCandidate, MedicalParseRequest
from gutcare.shared.errors import Problem

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
EMAIL_TOKEN_MINUTES = 10
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15
password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("gutcare-dummy-password-not-for-login")
logger = logging.getLogger("gutcare.auth")


class EmailProvider(Protocol):
    def send_verification(self, recipient: str, token: str) -> None: ...

    def send_password_reset(self, recipient: str, token: str) -> None: ...


class RateLimiter(Protocol):
    def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None: ...


class SmtpEmailVerificationProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send_verification(self, recipient: str, token: str) -> None:
        message = EmailMessage()
        message["Subject"] = "GutCare 邮箱验证"
        message["From"] = self._settings.smtp_sender
        message["To"] = recipient
        message.set_content(f"请在 GutCare APP 中输入以下一次性验证令牌：\n\n{token}\n")
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as smtp:
            if self._settings.smtp_starttls:
                smtp.starttls()
            if self._settings.smtp_username:
                smtp.login(self._settings.smtp_username, self._settings.smtp_password or "")
            smtp.send_message(message)

    def send_password_reset(self, recipient: str, token: str) -> None:
        message = EmailMessage()
        message["Subject"] = "GutCare 密码重置"
        message["From"] = self._settings.smtp_sender
        message["To"] = recipient
        message.set_content(f"请在 GutCare APP 中输入以下一次性重置令牌：\n\n{token}\n")
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=10) as smtp:
            if self._settings.smtp_starttls:
                smtp.starttls()
            if self._settings.smtp_username:
                smtp.login(self._settings.smtp_username, self._settings.smtp_password or "")
            smtp.send_message(message)


class MailpitEmailVerificationProvider(SmtpEmailVerificationProvider):
    """Local and test mail delivery through the standard SMTP Mailpit endpoint."""


class RedisRateLimiter:
    def __init__(self, client: Redis, window_seconds: int = 600) -> None:
        self._client = client
        self._window_seconds = window_seconds

    def check(self, scope: str, actor_hash: str, source_hash: str, limit: int) -> None:
        for subject in (actor_hash, source_hash):
            key = f"gutcare:auth:limit:{scope}:{subject}"
            with self._client.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, self._window_seconds)
                count = cast(int, pipeline.execute()[0])
            if count > limit:
                raise Problem(429, "RATE_LIMITED", "Too many requests", "Please try again later.")


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = ACCESS_TOKEN_MINUTES * 60


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: UUID
    session_id: UUID


ConsentType = Literal[
    "privacy_policy",
    "health_data_processing",
    "mood_data_processing",
    "mood_ai_sharing",
    "sensitive_image",
    "third_party_ai",
    "push_notification",
]


@dataclass(frozen=True, slots=True)
class PatientProfileData:
    id: UUID
    nickname: str | None
    birth_year: int
    timezone: str
    profile_version: int


@dataclass(frozen=True, slots=True)
class ConsentDecisionData:
    consent_type: ConsentType
    policy_version: str
    granted: bool
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class ConsentStatusData:
    consent_type: ConsentType
    policy_version: str | None
    granted: bool
    decided_at: datetime | None
    revoked_at: datetime | None


class AuthService:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        email_provider: EmailProvider | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        if email_provider is None:
            provider_type = (
                MailpitEmailVerificationProvider
                if settings.env in {"local", "test"}
                else SmtpEmailVerificationProvider
            )
            email_provider = provider_type(settings)
        self._email_provider = email_provider
        self._rate_limiter = rate_limiter

    def _required_setting(self, name: str, value: str | None) -> str:
        if not value:
            raise RuntimeError(f"Required authentication setting is missing: {name}")
        return value

    def _email_hash(self, email: str) -> str:
        pepper = self._required_setting(
            "AUTH_EMAIL_LOOKUP_PEPPER", self._settings.email_lookup_pepper
        )
        if len(pepper) < 32:
            raise RuntimeError("Email lookup pepper must contain at least 32 characters")
        return email_lookup_hash(email, pepper)

    def _source_hash(self, source: str) -> str:
        pepper = self._required_setting(
            "AUTH_EMAIL_LOOKUP_PEPPER", self._settings.email_lookup_pepper
        )
        if len(pepper) < 32:
            raise RuntimeError("Email lookup pepper must contain at least 32 characters")
        return email_lookup_hash(source, pepper)

    def _limit(self, scope: str, actor_hash: str, source: str, limit: int = 5) -> None:
        if self._rate_limiter is None:
            raise RuntimeError("Redis rate limiter is not configured")
        self._rate_limiter.check(scope, actor_hash, self._source_hash(source), limit)

    def _new_access_token(self, user_id: UUID, session_id: UUID) -> str:
        key = self._required_setting("AUTH_JWT_SIGNING_KEY", self._settings.jwt_signing_key)
        if len(key.encode()) < 32:
            raise RuntimeError("JWT signing key must contain at least 32 bytes")
        now = utc_now()
        claims = {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
        }
        return jwt.encode(claims, key, algorithm="HS256")

    def _new_session(
        self,
        db: Session,
        account: UserAccount,
        family_id: UUID | None = None,
        parent_session_id: UUID | None = None,
    ) -> TokenPair:
        raw_refresh = new_opaque_token()
        session_id = uuid4()
        db.add(
            RefreshSession(
                id=session_id,
                user_id=account.id,
                family_id=family_id if family_id is not None else session_id,
                parent_session_id=parent_session_id,
                token_hash=token_digest(raw_refresh),
                expires_at=utc_now() + timedelta(days=REFRESH_TOKEN_DAYS),
            )
        )
        db.flush()
        if parent_session_id is not None:
            parent_session = db.get(RefreshSession, parent_session_id)
            if parent_session is not None:
                parent_session.replaced_by_session_id = session_id
        return TokenPair(
            access_token=self._new_access_token(account.id, session_id),
            refresh_token=raw_refresh,
        )

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
        if not health_data_processing_consent:
            raise Problem(422, "VALIDATION_ERROR", "Health data processing consent is required")
        privacy_policy_hash = self._consent_summary_hash("privacy_policy", privacy_policy_version)
        health_policy_hash = self._consent_summary_hash(
            "health_data_processing", health_data_processing_policy_version
        )
        email = normalize_email(email_value)
        email_hash = self._email_hash(email)
        self._limit("register", email_hash, source)
        password_hash = password_hasher.hash(password)
        encryption_key = self._required_setting(
            "AUTH_EMAIL_ENCRYPTION_KEY", self._settings.email_encryption_key
        )
        raw_token = new_opaque_token()
        operation_id = uuid4()
        now = utc_now()

        with self._sessions.begin() as db:
            account = db.scalar(
                select(UserAccount)
                .where(UserAccount.email_lookup_hash == email_hash)
                .with_for_update()
            )
            if account is not None and account.status != "pending_verification":
                return operation_id
            if account is None:
                account = UserAccount(
                    email_ciphertext=encrypt_email(email, encryption_key),
                    email_lookup_hash=email_hash,
                    password_hash=password_hash,
                    status="pending_verification",
                    failed_login_count=0,
                )
                db.add(account)
                db.flush()
                db.execute(
                    text("SELECT set_config('app.user_id', :user_id, true)"),
                    {"user_id": str(account.id)},
                )
                profile = PatientProfile(
                    user_id=account.id,
                    nickname=None,
                    birth_year=birth_year,
                    timezone="Asia/Shanghai",
                    profile_version=1,
                )
                db.add(profile)
                db.flush()
                db.execute(
                    text("SELECT set_config('app.patient_id', :patient_id, true)"),
                    {"patient_id": str(profile.id)},
                )
                db.add(
                    PatientConsent(
                        patient_id=profile.id,
                        consent_type="privacy_policy",
                        document_version=privacy_policy_version,
                        granted=True,
                        decided_at=now,
                        metadata_json={
                            "channel": "mobile_app",
                            "notice_summary_hash": privacy_policy_hash,
                        },
                    )
                )
                db.add(
                    PatientConsent(
                        patient_id=profile.id,
                        consent_type="health_data_processing",
                        document_version=health_data_processing_policy_version,
                        granted=True,
                        decided_at=now,
                        metadata_json={
                            "channel": "mobile_app",
                            "notice_summary_hash": health_policy_hash,
                        },
                    )
                )
            else:
                account.email_ciphertext = encrypt_email(email, encryption_key)
            db.add(
                EmailVerificationToken(
                    user_id=account.id,
                    purpose="register",
                    token_hash=token_digest(raw_token),
                    expires_at=now + timedelta(minutes=EMAIL_TOKEN_MINUTES),
                    attempt_count=0,
                )
            )
        self._email_provider.send_verification(email, raw_token)
        return operation_id

    def verify_email(self, raw_token: str, source: str) -> None:
        token_hash = token_digest(raw_token)
        self._limit("verify_email", token_hash, source)
        now = utc_now()
        with self._sessions.begin() as db:
            verification = db.scalar(
                select(EmailVerificationToken)
                .where(
                    EmailVerificationToken.token_hash == token_hash,
                    EmailVerificationToken.purpose == "register",
                )
                .with_for_update()
            )
            if (
                verification is None
                or verification.used_at is not None
                or verification.expires_at <= now
            ):
                raise Problem(422, "VALIDATION_ERROR", "Invalid verification token")
            account = db.scalar(
                select(UserAccount).where(UserAccount.id == verification.user_id).with_for_update()
            )
            if account is None or account.status != "pending_verification":
                raise Problem(422, "VALIDATION_ERROR", "Invalid verification token")
            verification.used_at = now
            account.status = "active"
            account.updated_at = now

    def login(self, email_value: str, password: str, source: str) -> TokenPair:
        email = normalize_email(email_value)
        email_hash = self._email_hash(email)
        self._limit("login", email_hash, source, limit=10)
        now = utc_now()
        error: Problem | None = None
        tokens: TokenPair | None = None
        with self._sessions.begin() as db:
            account = db.scalar(
                select(UserAccount)
                .where(
                    UserAccount.email_lookup_hash == email_hash, UserAccount.deleted_at.is_(None)
                )
                .with_for_update()
            )
            if account is None:
                password_hasher.verify(password, DUMMY_PASSWORD_HASH)
                error = Problem(401, "INVALID_CREDENTIALS", "Invalid email or password")
            elif account.status == "locked":
                if account.locked_until is not None and account.locked_until > now:
                    error = Problem(
                        429, "RATE_LIMITED", "Too many requests", "Please try again later."
                    )
                else:
                    account.status = "active"
                    account.failed_login_count = 0
                    account.locked_until = None
            if error is None and account is not None:
                if account.status == "pending_verification":
                    password_hasher.verify(password, DUMMY_PASSWORD_HASH)
                    error = Problem(401, "INVALID_CREDENTIALS", "Invalid email or password")
                elif account.status != "active":
                    password_hasher.verify(password, DUMMY_PASSWORD_HASH)
                    error = Problem(401, "INVALID_CREDENTIALS", "Invalid email or password")
                elif not password_hasher.verify(password, account.password_hash):
                    account.failed_login_count += 1
                    account.updated_at = now
                    if account.failed_login_count >= LOGIN_FAILURE_LIMIT:
                        account.status = "locked"
                        account.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
                        error = Problem(
                            429, "RATE_LIMITED", "Too many requests", "Please try again later."
                        )
                    else:
                        error = Problem(401, "INVALID_CREDENTIALS", "Invalid email or password")
                else:
                    account.failed_login_count = 0
                    account.last_login_at = now
                    account.updated_at = now
                    tokens = self._new_session(db, account)
        if error is not None:
            raise error
        if tokens is None:
            raise RuntimeError("Authentication completed without a result")
        return tokens

    def refresh(self, raw_refresh: str) -> TokenPair:
        digest = token_digest(raw_refresh)
        now = utc_now()
        error: Problem | None = None
        tokens: TokenPair | None = None
        with self._sessions.begin() as db:
            presented = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == digest))
            if presented is None:
                raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")

            # family_id is the root session ID. Locking this stable row serializes
            # every refresh and replay in one family, including different descendants.
            family_root = db.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == presented.family_id)
                .with_for_update()
            )
            if family_root is None or family_root.id != presented.family_id:
                raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")

            # Under READ COMMITTED this statement runs after any prior family lock
            # holder commits, so force-refresh the identity-map row before deciding.
            old_session = db.scalar(
                select(RefreshSession)
                .where(RefreshSession.token_hash == digest)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if old_session is None or old_session.family_id != family_root.id:
                raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
            if old_session.revoked_at is not None:
                self._revoke_family(db, family_root.id, now)
                error = Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
            elif old_session.expires_at <= now:
                raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
            if error is not None:
                account = None
            else:
                account = db.scalar(
                    select(UserAccount)
                    .where(UserAccount.id == old_session.user_id)
                    .with_for_update()
                )
            if error is None and (account is None or account.status != "active"):
                self._revoke_family(db, family_root.id, now)
                error = Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
            elif error is None and account is not None:
                old_session.revoked_at = now
                tokens = self._new_session(
                    db,
                    account,
                    family_id=old_session.family_id,
                    parent_session_id=old_session.id,
                )
        if error is not None:
            raise error
        if tokens is None:
            raise RuntimeError("Refresh completed without a result")
        return tokens

    @staticmethod
    def _revoke_family(db: Session, family_id: UUID, now: datetime) -> None:
        db.execute(
            text(
                "UPDATE iam.refresh_session SET revoked_at = :now "
                "WHERE family_id = :family_id AND revoked_at IS NULL"
            ),
            {"now": now, "family_id": family_id},
        )

    def request_password_reset(self, email_value: str, source: str) -> UUID:
        email = normalize_email(email_value)
        email_hash = self._email_hash(email)
        self._limit("password_reset", email_hash, source)
        raw_token = new_opaque_token()
        operation_id = uuid4()
        now = utc_now()
        recipient: str | None = None
        with self._sessions.begin() as db:
            account = db.scalar(
                select(UserAccount)
                .where(
                    UserAccount.email_lookup_hash == email_hash,
                    UserAccount.status == "active",
                    UserAccount.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if account is not None:
                recipient = decrypt_email(
                    account.email_ciphertext,
                    self._required_setting(
                        "AUTH_EMAIL_ENCRYPTION_KEY", self._settings.email_encryption_key
                    ),
                )
                db.add(
                    EmailVerificationToken(
                        user_id=account.id,
                        purpose="password_reset",
                        token_hash=token_digest(raw_token),
                        expires_at=now + timedelta(minutes=EMAIL_TOKEN_MINUTES),
                        attempt_count=0,
                    )
                )
        if recipient is not None:
            try:
                self._email_provider.send_password_reset(recipient, raw_token)
            except (smtplib.SMTPException, OSError):
                # Keep the response indistinguishable from the unknown-account case.
                logger.warning("password_reset_delivery_failed")
        return operation_id

    def confirm_password_reset(self, raw_token: str, new_password: str, source: str) -> None:
        token_hash = token_digest(raw_token)
        self._limit("password_reset_confirm", token_hash, source)
        now = utc_now()
        new_hash = password_hasher.hash(new_password)
        with self._sessions.begin() as db:
            token = db.scalar(
                select(EmailVerificationToken)
                .where(
                    EmailVerificationToken.token_hash == token_hash,
                    EmailVerificationToken.purpose == "password_reset",
                )
                .with_for_update()
            )
            if token is None or token.used_at is not None or token.expires_at <= now:
                raise Problem(422, "VALIDATION_ERROR", "Invalid password reset token")
            account = db.scalar(
                select(UserAccount).where(UserAccount.id == token.user_id).with_for_update()
            )
            if account is None or account.status != "active":
                raise Problem(422, "VALIDATION_ERROR", "Invalid password reset token")
            token.used_at = now
            account.password_hash = new_hash
            account.failed_login_count = 0
            account.locked_until = None
            account.updated_at = now
            db.execute(
                text(
                    "UPDATE iam.email_verification_token SET used_at = :now "
                    "WHERE user_id = :user_id AND purpose = 'password_reset' "
                    "AND used_at IS NULL"
                ),
                {"now": now, "user_id": account.id},
            )
            db.execute(
                text(
                    "UPDATE iam.refresh_session SET revoked_at = :now "
                    "WHERE user_id = :user_id AND revoked_at IS NULL"
                ),
                {"now": now, "user_id": account.id},
            )

    def authenticate_access_token(self, raw_access: str) -> AuthContext:
        key = self._required_setting("AUTH_JWT_SIGNING_KEY", self._settings.jwt_signing_key)
        if len(key.encode()) < 32:
            raise RuntimeError("JWT signing key must contain at least 32 bytes")
        try:
            claims = jwt.decode(
                raw_access,
                key,
                algorithms=["HS256"],
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
            )
            context = AuthContext(user_id=UUID(claims["sub"]), session_id=UUID(claims["sid"]))
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required") from None
        now = utc_now()
        with self._sessions() as db:
            session = db.scalar(
                select(RefreshSession).where(
                    RefreshSession.id == context.session_id,
                    RefreshSession.user_id == context.user_id,
                    RefreshSession.revoked_at.is_(None),
                    RefreshSession.expires_at > now,
                )
            )
            account = db.get(UserAccount, context.user_id)
            if session is None or account is None or account.status != "active":
                raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        return context

    def logout(self, context: AuthContext) -> None:
        with self._sessions.begin() as db:
            session = db.scalar(
                select(RefreshSession)
                .where(
                    RefreshSession.id == context.session_id,
                    RefreshSession.user_id == context.user_id,
                )
                .with_for_update()
            )
            if session is not None and session.revoked_at is None:
                session.revoked_at = utc_now()

    def request_account_deletion(self, context: AuthContext) -> UUID:
        now = utc_now()
        with self._sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.user_id', :user_id, true)"),
                {"user_id": str(context.user_id)},
            )
            existing = db.scalar(
                select(AccountDeletionRequest)
                .where(AccountDeletionRequest.user_id == context.user_id)
                .with_for_update()
            )
            if existing is not None:
                return existing.id

            account = db.scalar(
                select(UserAccount).where(UserAccount.id == context.user_id).with_for_update()
            )
            if account is None or account.deleted_at is not None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Account not found")
            if account.status != "active":
                raise Problem(409, "IDEMPOTENCY_CONFLICT", "Account deletion is unavailable")

            profile = db.scalar(select(PatientProfile).where(PatientProfile.user_id == account.id))
            if profile is not None:
                db.execute(
                    text("SELECT set_config('app.patient_id', :patient_id, true)"),
                    {"patient_id": str(profile.id)},
                )
                db.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtextextended("
                        "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                    ),
                    {"patient_id": str(profile.id)},
                )
                for consent_type in ("health_data_processing", "third_party_ai"):
                    latest_consent = db.scalar(
                        select(PatientConsent)
                        .where(
                            PatientConsent.patient_id == profile.id,
                            PatientConsent.consent_type == consent_type,
                        )
                        .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
                        .limit(1)
                    )
                    if latest_consent is not None and latest_consent.granted:
                        consent_metadata = dict(latest_consent.metadata_json or {})
                        consent_metadata["channel"] = "account_deletion"
                        db.add(
                            PatientConsent(
                                patient_id=profile.id,
                                consent_type=consent_type,
                                document_version=latest_consent.document_version,
                                granted=False,
                                decided_at=now,
                                revoked_at=now,
                                metadata_json=consent_metadata,
                            )
                        )
                db.execute(
                    update(AnalysisTask)
                    .where(
                        AnalysisTask.patient_id == profile.id,
                        AnalysisTask.status.in_(("pending", "processing")),
                    )
                    .values(status="cancelled", lease_expires_at=None, updated_at=now),
                    {},
                )

            deletion = AccountDeletionRequest(
                user_id=account.id,
                status="pending",
                requested_at=now,
            )
            db.add(deletion)
            account.status = "deactivated"
            account.updated_at = now
            db.execute(
                text(
                    "UPDATE iam.refresh_session SET revoked_at = :now "
                    "WHERE user_id = :user_id AND revoked_at IS NULL"
                ),
                {"now": now, "user_id": account.id},
            )
            db.flush()
            return deletion.id

    @staticmethod
    def _set_patient_rls_context(db: Session, user_id: UUID) -> PatientProfile:
        db.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )
        profile = db.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == user_id,
                PatientProfile.deleted_at.is_(None),
            )
        )
        if profile is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Patient profile not found")
        db.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(profile.id)},
        )
        return profile

    @staticmethod
    def _profile_data(profile: PatientProfile) -> PatientProfileData:
        return PatientProfileData(
            id=profile.id,
            nickname=profile.nickname,
            birth_year=profile.birth_year,
            timezone=profile.timezone,
            profile_version=profile.profile_version,
        )

    def get_my_profile(self, context: AuthContext) -> PatientProfileData:
        with self._sessions.begin() as db:
            profile = self._set_patient_rls_context(db, context.user_id)
            return self._profile_data(profile)

    def get_my_consents(self, context: AuthContext) -> list[ConsentStatusData]:
        consent_types: tuple[ConsentType, ...] = (
            "health_data_processing",
            "mood_data_processing",
            "mood_ai_sharing",
            "third_party_ai",
            "sensitive_image",
            "push_notification",
        )
        with self._sessions.begin() as db:
            profile = self._set_patient_rls_context(db, context.user_id)
            decisions = db.scalars(
                select(PatientConsent)
                .where(
                    PatientConsent.patient_id == profile.id,
                    PatientConsent.consent_type.in_(consent_types),
                )
                .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
            ).all()
            latest: dict[str, PatientConsent] = {}
            for decision in decisions:
                latest.setdefault(decision.consent_type, decision)
            return [
                ConsentStatusData(
                    consent_type=consent_type,
                    policy_version=latest[consent_type].document_version
                    if consent_type in latest
                    else None,
                    granted=latest[consent_type].granted if consent_type in latest else False,
                    decided_at=latest[consent_type].decided_at if consent_type in latest else None,
                    revoked_at=latest[consent_type].revoked_at if consent_type in latest else None,
                )
                for consent_type in consent_types
            ]

    def patch_my_profile(
        self,
        context: AuthContext,
        profile_version: int,
        changes: dict[str, str | int | None],
    ) -> PatientProfileData:
        if "timezone" in changes:
            timezone_value = changes["timezone"]
            if not isinstance(timezone_value, str):
                raise Problem(422, "VALIDATION_ERROR", "Invalid patient timezone")
            try:
                ZoneInfo(timezone_value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise Problem(422, "VALIDATION_ERROR", "Invalid patient timezone") from exc
        with self._sessions.begin() as db:
            scoped_profile = self._set_patient_rls_context(db, context.user_id)
            profile = db.scalar(
                select(PatientProfile)
                .where(PatientProfile.id == scoped_profile.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if profile is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Patient profile not found")
            if profile.profile_version != profile_version:
                raise Problem(
                    409,
                    "RECORD_VERSION_CONFLICT",
                    "Patient profile has changed",
                    "Reload the profile and retry your update.",
                )
            if not changes:
                return self._profile_data(profile)
            for field, value in changes.items():
                if field not in {"nickname", "birth_year", "timezone"}:
                    raise RuntimeError("Unsupported patient profile update field")
                setattr(profile, field, value)
            profile.profile_version += 1
            profile.updated_at = utc_now()
            db.flush()
            return self._profile_data(profile)

    def _consent_summary_hash(self, consent_type: ConsentType, supplied_version: str) -> str:
        config = {
            "privacy_policy": (
                "PRIVACY_POLICY_VERSION",
                self._settings.privacy_policy_version,
                "PRIVACY_POLICY_SUMMARY_HASH",
                self._settings.privacy_policy_summary_hash,
            ),
            "health_data_processing": (
                "HEALTH_DATA_PROCESSING_POLICY_VERSION",
                self._settings.health_data_processing_policy_version,
                "HEALTH_DATA_PROCESSING_SUMMARY_HASH",
                self._settings.health_data_processing_summary_hash,
            ),
            "mood_data_processing": (
                "MOOD_DATA_PROCESSING_POLICY_VERSION",
                self._settings.mood_data_processing_policy_version,
                "MOOD_DATA_PROCESSING_SUMMARY_HASH",
                self._settings.mood_data_processing_summary_hash,
            ),
            "mood_ai_sharing": (
                "MOOD_AI_SHARING_POLICY_VERSION",
                self._settings.mood_ai_sharing_policy_version,
                "MOOD_AI_SHARING_SUMMARY_HASH",
                self._settings.mood_ai_sharing_summary_hash,
            ),
            "sensitive_image": (
                "SENSITIVE_IMAGE_POLICY_VERSION",
                self._settings.sensitive_image_policy_version,
                "SENSITIVE_IMAGE_SUMMARY_HASH",
                self._settings.sensitive_image_summary_hash,
            ),
            "third_party_ai": (
                "THIRD_PARTY_AI_POLICY_VERSION",
                self._settings.third_party_ai_policy_version,
                "THIRD_PARTY_AI_SUMMARY_HASH",
                self._settings.third_party_ai_summary_hash,
            ),
            "push_notification": (
                "PUSH_NOTIFICATION_POLICY_VERSION",
                self._settings.push_notification_policy_version,
                "PUSH_NOTIFICATION_SUMMARY_HASH",
                self._settings.push_notification_summary_hash,
            ),
        }
        version_setting, configured_version, hash_setting, hash_value = config[consent_type]
        allowed_version = self._required_setting(version_setting, configured_version)
        if supplied_version != allowed_version:
            raise Problem(422, "VALIDATION_ERROR", "Unsupported consent policy version")
        summary_hash = self._required_setting(hash_setting, hash_value)
        if len(summary_hash) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in summary_hash
        ):
            raise RuntimeError("Consent notice summary hash must be SHA-256 hex")
        return summary_hash.lower()

    def record_consent(
        self,
        context: AuthContext,
        consent_type: ConsentType,
        policy_version: str,
        granted: bool,
    ) -> ConsentDecisionData:
        if consent_type == "privacy_policy":
            raise Problem(
                422,
                "VALIDATION_ERROR",
                "Privacy policy withdrawal must use account deletion",
            )
        summary_hash: str | None = None
        if granted:
            if consent_type in SUPPORTED_NOTICE_TYPES:
                notice = resolve_current_consent_notice(self._settings, consent_type)
                if notice is None:
                    raise Problem(
                        503,
                        "CONSENT_NOTICE_UNAVAILABLE",
                        "Current consent notice is unavailable",
                    )
                if notice.policy_version != policy_version:
                    raise Problem(422, "VALIDATION_ERROR", "Unsupported consent policy version")
                summary_hash = notice.summary_sha256
            else:
                summary_hash = self._consent_summary_hash(consent_type, policy_version)
        now = utc_now()
        with self._sessions.begin() as db:
            profile = self._set_patient_rls_context(db, context.user_id)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                ),
                {"patient_id": str(profile.id)},
            )
            if not granted:
                latest = db.scalar(
                    select(PatientConsent)
                    .where(
                        PatientConsent.patient_id == profile.id,
                        PatientConsent.consent_type == consent_type,
                    )
                    .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
                    .with_for_update()
                )
                if latest is None or not latest.granted:
                    raise Problem(409, "CONSENT_NOT_ACTIVE", "No active consent to withdraw")
                if latest.document_version != policy_version:
                    raise Problem(422, "VALIDATION_ERROR", "Consent policy version does not match")
                summary_hash = (latest.metadata_json or {}).get("notice_summary_hash")
                if (
                    not isinstance(summary_hash, str)
                    or len(summary_hash) != 64
                    or any(character not in "0123456789abcdef" for character in summary_hash)
                ):
                    raise RuntimeError("Stored consent notice summary hash is invalid")
            db.add(
                PatientConsent(
                    patient_id=profile.id,
                    consent_type=consent_type,
                    document_version=policy_version,
                    granted=granted,
                    decided_at=now,
                    revoked_at=None if granted else now,
                    metadata_json={
                        "channel": "mobile_app",
                        "notice_summary_hash": summary_hash,
                    },
                )
            )
            if not granted and consent_type in {"health_data_processing", "third_party_ai"}:
                db.execute(
                    update(AnalysisTask)
                    .where(
                        AnalysisTask.patient_id == profile.id,
                        AnalysisTask.status.in_(("pending", "processing")),
                    )
                    .values(status="cancelled", lease_expires_at=None, updated_at=now),
                    {},
                )
                active_request_ids = list(
                    db.scalars(
                        select(MedicalParseRequest.id).where(
                            MedicalParseRequest.patient_id == profile.id,
                            MedicalParseRequest.status.in_(
                                ("pending", "processing", "needs_confirmation")
                            ),
                        )
                    )
                )
                db.execute(
                    update(MedicalParseRequest)
                    .where(
                        MedicalParseRequest.patient_id == profile.id,
                        MedicalParseRequest.status.in_(
                            ("pending", "processing", "needs_confirmation")
                        ),
                    )
                    .values(status="invalidated", finished_at=now),
                    {},
                )
                if active_request_ids:
                    db.execute(
                        update(MedicalFieldCandidate)
                        .where(
                            MedicalFieldCandidate.patient_id == profile.id,
                            MedicalFieldCandidate.request_id.in_(active_request_ids),
                        )
                        .values(excerpt=None, source_locator=None, review_status="invalidated")
                    )
            elif not granted and consent_type in {"mood_data_processing", "mood_ai_sharing"}:
                db.execute(
                    text("""UPDATE analysis.analysis_task t
                        SET status='cancelled', lease_expires_at=NULL, result_payload=NULL,
                            updated_at=:now
                        WHERE t.patient_id=:patient AND t.status IN ('pending','processing')
                          AND EXISTS (
                            SELECT 1 FROM analysis.task_input_snapshot s,
                                 jsonb_array_elements(s.snapshot_payload->'records') r
                            WHERE s.task_id=t.id AND s.patient_id=t.patient_id
                              AND r->>'record_type'='mood_record'
                          )"""),
                    {"patient": str(profile.id), "now": now},
                )
            db.flush()
        return ConsentDecisionData(
            consent_type=consent_type,
            policy_version=policy_version,
            granted=granted,
            decided_at=now,
        )
