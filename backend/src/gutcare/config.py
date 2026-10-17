"""Validated application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    env: Literal["local", "test", "staging", "production"] = Field(
        default="local",
        validation_alias=AliasChoices("APP__ENV", "APP_ENV", "env"),
    )
    service_name: str = Field(
        default="gutcare-business-api",
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("APP__SERVICE_NAME", "APP_SERVICE_NAME", "service_name"),
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        validation_alias=AliasChoices("APP__LOG_LEVEL", "APP_LOG_LEVEL", "log_level"),
    )
    metrics_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "OPS__METRICS_ENABLED", "OPS_METRICS_ENABLED", "metrics_enabled"
        ),
    )
    metrics_token: str | None = Field(
        default=None,
        repr=False,
        min_length=32,
        validation_alias=AliasChoices("OPS__METRICS_TOKEN", "OPS_METRICS_TOKEN", "metrics_token"),
    )
    public_base_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost"),
        validation_alias=AliasChoices(
            "APP__PUBLIC_BASE_URL", "APP_PUBLIC_BASE_URL", "public_base_url"
        ),
    )
    database_url: PostgresDsn | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("DATABASE__URL", "DATABASE_URL", "database_url"),
    )
    worker_database_url: PostgresDsn | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "WORKER_DATABASE__URL", "WORKER_DATABASE_URL", "worker_database_url"
        ),
    )
    analysis_worker_database_url: PostgresDsn | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "ANALYSIS_WORKER_DATABASE__URL",
            "ANALYSIS_WORKER_DATABASE_URL",
            "analysis_worker_database_url",
        ),
    )
    privacy_worker_database_url: PostgresDsn | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "PRIVACY_WORKER_DATABASE__URL",
            "PRIVACY_WORKER_DATABASE_URL",
            "privacy_worker_database_url",
        ),
    )
    redis_url: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("REDIS__URL", "REDIS_URL", "redis_url"),
    )
    object_storage_endpoint: AnyHttpUrl | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "FILES__ENDPOINT", "FILES_ENDPOINT", "object_storage_endpoint"
        ),
    )
    object_storage_public_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FILES__PUBLIC_URL", "FILES_PUBLIC_URL", "object_storage_public_url"
        ),
    )
    object_storage_access_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "FILES__ACCESS_KEY", "FILES_ACCESS_KEY", "object_storage_access_key"
        ),
    )
    object_storage_secret_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "FILES__SECRET_KEY", "FILES_SECRET_KEY", "object_storage_secret_key"
        ),
    )
    object_storage_bucket: str = Field(
        default="gutcare-files",
        min_length=3,
        max_length=63,
        validation_alias=AliasChoices("FILES__BUCKET", "FILES_BUCKET", "object_storage_bucket"),
    )
    clamav_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FILES__CLAMAV_HOST", "FILES_CLAMAV_HOST", "clamav_host"),
    )
    clamav_port: int = Field(
        default=3310,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("FILES__CLAMAV_PORT", "FILES_CLAMAV_PORT", "clamav_port"),
    )
    clamav_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=120,
        validation_alias=AliasChoices(
            "FILES__CLAMAV_TIMEOUT_SECONDS",
            "FILES_CLAMAV_TIMEOUT_SECONDS",
            "clamav_timeout_seconds",
        ),
    )
    files_capability_secret: str | None = Field(
        default=None,
        repr=False,
        min_length=32,
        validation_alias=AliasChoices(
            "FILES__CAPABILITY_SECRET", "FILES_CAPABILITY_SECRET", "files_capability_secret"
        ),
    )
    agent_service_token: str | None = Field(
        default=None,
        repr=False,
        min_length=32,
        validation_alias=AliasChoices(
            "AGENT__SERVICE_TOKEN", "AGENT_SERVICE_TOKEN", "agent_service_token"
        ),
    )
    email_lookup_pepper: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "AUTH__EMAIL_LOOKUP_PEPPER", "AUTH_EMAIL_LOOKUP_PEPPER", "email_lookup_pepper"
        ),
    )
    mood_idempotency_hmac_key: str | None = Field(
        default=None,
        repr=False,
        min_length=32,
        validation_alias=AliasChoices(
            "MOOD__IDEMPOTENCY_HMAC_KEY",
            "MOOD_IDEMPOTENCY_HMAC_KEY",
            "mood_idempotency_hmac_key",
        ),
    )
    email_encryption_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "AUTH__EMAIL_ENCRYPTION_KEY", "AUTH_EMAIL_ENCRYPTION_KEY", "email_encryption_key"
        ),
    )
    export_kek: str | None = Field(
        default=None,
        repr=False,
        min_length=32,
        validation_alias=AliasChoices("EXPORT_KEK", "export_kek"),
    )
    jwt_signing_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "AUTH__JWT_SIGNING_KEY", "AUTH_JWT_SIGNING_KEY", "jwt_signing_key"
        ),
    )
    jwt_issuer: str = Field(
        default="gutcare-business-api",
        validation_alias=AliasChoices("AUTH__JWT_ISSUER", "AUTH_JWT_ISSUER", "jwt_issuer"),
    )
    jwt_audience: str = Field(
        default="gutcare-mobile-app",
        validation_alias=AliasChoices("AUTH__JWT_AUDIENCE", "AUTH_JWT_AUDIENCE", "jwt_audience"),
    )
    smtp_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("MAIL__SMTP_HOST", "MAIL_SMTP_HOST", "smtp_host"),
    )
    smtp_port: int = Field(
        default=1025,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("MAIL__SMTP_PORT", "MAIL_SMTP_PORT", "smtp_port"),
    )
    smtp_sender: str = Field(
        default="no-reply@gutcare.invalid",
        validation_alias=AliasChoices("MAIL__SENDER", "MAIL_SENDER", "smtp_sender"),
    )
    smtp_starttls: bool = Field(
        default=False,
        validation_alias=AliasChoices("MAIL__STARTTLS", "MAIL_STARTTLS", "smtp_starttls"),
    )
    smtp_username: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("MAIL__USERNAME", "MAIL_USERNAME", "smtp_username"),
    )
    smtp_password: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("MAIL__PASSWORD", "MAIL_PASSWORD", "smtp_password"),
    )
    privacy_policy_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__POLICY_SUMMARY_HASH",
            "PRIVACY_POLICY_SUMMARY_HASH",
            "privacy_policy_summary_hash",
        ),
    )
    health_data_processing_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__HEALTH_DATA_PROCESSING_SUMMARY_HASH",
            "HEALTH_DATA_PROCESSING_SUMMARY_HASH",
            "health_data_processing_summary_hash",
        ),
    )
    mood_data_processing_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__MOOD_DATA_PROCESSING_SUMMARY_HASH",
            "MOOD_DATA_PROCESSING_SUMMARY_HASH",
            "mood_data_processing_summary_hash",
        ),
    )
    mood_ai_sharing_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__MOOD_AI_SHARING_SUMMARY_HASH",
            "MOOD_AI_SHARING_SUMMARY_HASH",
            "mood_ai_sharing_summary_hash",
        ),
    )
    sensitive_image_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__SENSITIVE_IMAGE_SUMMARY_HASH",
            "SENSITIVE_IMAGE_SUMMARY_HASH",
            "sensitive_image_summary_hash",
        ),
    )
    third_party_ai_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__THIRD_PARTY_AI_SUMMARY_HASH",
            "THIRD_PARTY_AI_SUMMARY_HASH",
            "third_party_ai_summary_hash",
        ),
    )
    push_notification_summary_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__PUSH_NOTIFICATION_SUMMARY_HASH",
            "PUSH_NOTIFICATION_SUMMARY_HASH",
            "push_notification_summary_hash",
        ),
    )
    privacy_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__POLICY_VERSION", "PRIVACY_POLICY_VERSION", "privacy_policy_version"
        ),
    )
    health_data_processing_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__HEALTH_DATA_PROCESSING_POLICY_VERSION",
            "HEALTH_DATA_PROCESSING_POLICY_VERSION",
            "health_data_processing_policy_version",
        ),
    )
    mood_data_processing_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__MOOD_DATA_PROCESSING_POLICY_VERSION",
            "MOOD_DATA_PROCESSING_POLICY_VERSION",
            "mood_data_processing_policy_version",
        ),
    )
    mood_ai_sharing_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__MOOD_AI_SHARING_POLICY_VERSION",
            "MOOD_AI_SHARING_POLICY_VERSION",
            "mood_ai_sharing_policy_version",
        ),
    )
    sensitive_image_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__SENSITIVE_IMAGE_POLICY_VERSION",
            "SENSITIVE_IMAGE_POLICY_VERSION",
            "sensitive_image_policy_version",
        ),
    )
    third_party_ai_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__THIRD_PARTY_AI_POLICY_VERSION",
            "THIRD_PARTY_AI_POLICY_VERSION",
            "third_party_ai_policy_version",
        ),
    )
    push_notification_policy_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PRIVACY__PUSH_NOTIFICATION_POLICY_VERSION",
            "PUSH_NOTIFICATION_POLICY_VERSION",
            "push_notification_policy_version",
        ),
    )

    @model_validator(mode="after")
    def validate_metrics_exposure(self) -> "Settings":
        if self.metrics_enabled and not self.metrics_token:
            raise ValueError("OPS_METRICS_TOKEN is required when metrics exposure is enabled")
        if self.env == "production":
            registration_notice_config = {
                "PRIVACY_POLICY_VERSION": self.privacy_policy_version,
                "PRIVACY_POLICY_SUMMARY_HASH": self.privacy_policy_summary_hash,
                "HEALTH_DATA_PROCESSING_POLICY_VERSION": (
                    self.health_data_processing_policy_version
                ),
                "HEALTH_DATA_PROCESSING_SUMMARY_HASH": (self.health_data_processing_summary_hash),
            }
            missing = [name for name, value in registration_notice_config.items() if not value]
            if missing:
                raise ValueError(
                    "Production registration notice configuration is incomplete: "
                    + ", ".join(sorted(missing))
                )
            for name in ("PRIVACY_POLICY_VERSION", "HEALTH_DATA_PROCESSING_POLICY_VERSION"):
                version = registration_notice_config[name]
                if version is not None and version.lower().startswith(
                    (
                        "test-",
                        "test_",
                        "dev-",
                        "dev_",
                        "development-",
                        "development_",
                    )
                ):
                    raise ValueError(f"{name} must reference a legally approved production notice")
            for name in (
                "PRIVACY_POLICY_SUMMARY_HASH",
                "HEALTH_DATA_PROCESSING_SUMMARY_HASH",
            ):
                summary_hash = registration_notice_config[name]
                if (
                    summary_hash is None
                    or len(summary_hash) != 64
                    or any(character not in "0123456789abcdefABCDEF" for character in summary_hash)
                ):
                    raise ValueError(f"{name} must be a SHA-256 hex digest")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
