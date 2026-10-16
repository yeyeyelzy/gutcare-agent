"""Create the F01 email authentication and registration consent schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_f01_email_auth"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS iam"))
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS health"))
    op.execute(sa.text("GRANT USAGE ON SCHEMA iam, health TO gutcare_app, gutcare_worker"))
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA iam, health "
            "GRANT SELECT, INSERT, UPDATE ON TABLES TO gutcare_app"
        )
    )
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA iam, health "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gutcare_worker"
        )
    )

    op.create_table(
        "user_account",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("email_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("email_lookup_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("failed_login_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending_verification', 'active', 'locked', 'deactivated')",
            name="ck_user_account_status",
        ),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_user_account_failed_login_count"),
        schema="iam",
    )
    op.create_index(
        "uq_user_account_email_lookup_hash_live",
        "user_account",
        ["email_lookup_hash"],
        unique=True,
        schema="iam",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "email_verification_token",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "purpose IN ('register', 'password_reset')", name="ck_email_token_purpose"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_email_token_attempt_count"),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user_account.id"], ondelete="CASCADE"),
        schema="iam",
    )
    op.create_index(
        "ix_email_token_user_purpose_created",
        "email_verification_token",
        ["user_id", "purpose", "created_at"],
        schema="iam",
    )

    op.create_table(
        "refresh_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False, unique=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user_account.id"], ondelete="CASCADE"),
        schema="iam",
    )
    op.create_index(
        "ix_refresh_session_user_active",
        "refresh_session",
        ["user_id", "expires_at"],
        schema="iam",
    )

    op.create_table(
        "patient_profile",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nickname", sa.String(length=64)),
        sa.Column("avatar_object_id", postgresql.UUID(as_uuid=True)),
        sa.Column("birth_year", sa.SmallInteger(), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Shanghai", nullable=False),
        sa.Column("profile_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "birth_year BETWEEN 1900 AND 2100", name="ck_patient_profile_birth_year"
        ),
        sa.CheckConstraint("profile_version >= 1", name="ck_patient_profile_version"),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user_account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_patient_profile_user_id"),
        schema="health",
    )

    op.create_table(
        "patient_consent",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=48), nullable=False),
        sa.Column("document_version", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB()),
        sa.CheckConstraint(
            "consent_type IN ('privacy_policy', 'health_data_processing', 'sensitive_image', "
            "'third_party_ai', 'push_notification')",
            name="ck_patient_consent_type",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="health",
    )
    op.create_index(
        "ix_patient_consent_current",
        "patient_consent",
        ["patient_id", "consent_type", "decided_at"],
        schema="health",
    )
    op.execute(sa.text("ALTER TABLE health.patient_profile ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE health.patient_profile FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY patient_profile_isolation ON health.patient_profile "
            "USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid) "
            "WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)"
        )
    )
    op.execute(sa.text("ALTER TABLE health.patient_consent ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE health.patient_consent FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY patient_consent_isolation ON health.patient_consent "
            "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
            "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
    )
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA iam, health TO gutcare_app")
    )
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA iam, health "
            "TO gutcare_worker"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY patient_consent_isolation ON health.patient_consent"))
    op.execute(sa.text("DROP POLICY patient_profile_isolation ON health.patient_profile"))
    op.drop_index("ix_patient_consent_current", table_name="patient_consent", schema="health")
    op.drop_table("patient_consent", schema="health")
    op.drop_table("patient_profile", schema="health")
    op.drop_index("ix_refresh_session_user_active", table_name="refresh_session", schema="iam")
    op.drop_table("refresh_session", schema="iam")
    op.drop_index(
        "ix_email_token_user_purpose_created",
        table_name="email_verification_token",
        schema="iam",
    )
    op.drop_table("email_verification_token", schema="iam")
    op.drop_index("uq_user_account_email_lookup_hash_live", table_name="user_account", schema="iam")
    op.drop_table("user_account", schema="iam")
    op.execute(sa.text("DROP SCHEMA health"))
    op.execute(sa.text("DROP SCHEMA iam"))
