"""F13 durable deletion, inventory, audit and export operations."""

# ruff: noqa: E501 -- fixed SQL policy and CHECK expressions are intentionally kept literal.

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_f13_privacy_lifecycle"
down_revision: str | None = "0016_f07_activity_f11_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS privacy")
    op.add_column(
        "file_orphan_cleanup_job",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True)),
        schema="integration",
    )
    op.execute("""
        UPDATE integration.file_orphan_cleanup_job orphan
        SET patient_id = upload.patient_id
        FROM health.upload_session upload
        WHERE orphan.patient_id IS NULL
          AND orphan.bucket_name = upload.bucket_name
          AND orphan.object_key = upload.object_key
    """)
    op.create_foreign_key(
        "fk_file_orphan_cleanup_patient",
        "file_orphan_cleanup_job",
        "patient_profile",
        ["patient_id"],
        ["id"],
        source_schema="integration",
        referent_schema="health",
        ondelete="SET NULL",
    )
    op.execute("ALTER TABLE integration.file_orphan_cleanup_job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration.file_orphan_cleanup_job FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY file_orphan_cleanup_app_insert ON integration.file_orphan_cleanup_job FOR INSERT TO gutcare_app WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY file_orphan_cleanup_existing_worker ON integration.file_orphan_cleanup_job TO gutcare_worker USING (true) WITH CHECK (true)"
    )
    op.create_table(
        "deletion_operation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("account_hash", sa.CHAR(64), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True)),
        sa.Column("receipt_hash", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(48)),
        sa.CheckConstraint(
            "status IN ('pending','processing','overdue','completed','dead_letter')",
            name="ck_deletion_operation_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_deletion_operation_attempts"),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[A-Z0-9_]{1,48}$'",
            name="ck_deletion_operation_error_code",
        ),
        sa.UniqueConstraint("receipt_hash", name="uq_deletion_operation_receipt_hash"),
        schema="privacy",
    )
    op.create_index(
        "ix_deletion_operation_claim",
        "deletion_operation",
        ["status", "due_at", "lease_expires_at"],
        schema="privacy",
    )
    op.create_index(
        "uq_deletion_operation_live_account",
        "deletion_operation",
        ["account_hash"],
        unique=True,
        schema="privacy",
        postgresql_where=sa.text("status <> 'completed'"),
    )
    op.create_table(
        "deletion_step",
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_code", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(48)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("operation_id", "step_code"),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["privacy.deletion_operation.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed')",
            name="ck_deletion_step_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_deletion_step_attempts"),
        schema="privacy",
    )
    op.create_table(
        "object_inventory",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_name", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512)),
        sa.Column("version_id", sa.String(256)),
        sa.Column("key_digest_ciphertext", sa.LargeBinary()),
        sa.Column("source_code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(48)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["privacy.deletion_operation.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "operation_id",
            "bucket_name",
            "object_key",
            "version_id",
            name="uq_privacy_inventory_location",
        ),
        sa.CheckConstraint(
            "source_code IN ('file_object','upload_session','orphan','export')",
            name="ck_privacy_inventory_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending','deleting','deleted','failed')",
            name="ck_privacy_inventory_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_privacy_inventory_attempts"),
        sa.CheckConstraint(
            "(object_key IS NULL) OR (key_digest_ciphertext IS NULL)",
            name="ck_privacy_inventory_key_minimization",
        ),
        schema="privacy",
    )
    op.create_table(
        "export_operation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="preview"),
        sa.Column("categories", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("object_key", sa.String(512)),
        sa.Column("wrapped_dek", sa.LargeBinary()),
        sa.Column("capability_hash", sa.CHAR(64)),
        sa.Column("capability_expires_at", sa.DateTime(timezone=True)),
        sa.Column("capability_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(48)),
        sa.CheckConstraint(
            "status IN ('preview','pending','processing','ready','cancelled','expired','failed')",
            name="ck_export_operation_status",
        ),
        sa.CheckConstraint(
            "categories <@ ARRAY['profile','consents','medical_documents','files','diet','stool','symptoms','medication','activity','analysis','advice','alerts','notifications']::varchar[]",
            name="ck_export_operation_categories",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="privacy",
    )
    op.create_index(
        "ix_export_operation_patient",
        "export_operation",
        ["patient_id", "created_at"],
        schema="privacy",
    )
    op.create_table(
        "security_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("operation_hash", sa.CHAR(64), nullable=False),
        sa.Column("event_code", sa.String(48), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_code ~ '^[A-Z0-9_]{1,48}$'", name="ck_privacy_audit_event_code"),
        schema="privacy",
    )
    for table in (
        "deletion_operation",
        "deletion_step",
        "object_inventory",
        "export_operation",
        "security_audit",
    ):
        op.execute(f"ALTER TABLE privacy.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE privacy.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY deletion_operation_worker ON privacy.deletion_operation TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY deletion_operation_receipt_lookup ON privacy.deletion_operation FOR SELECT TO gutcare_app USING (receipt_hash = NULLIF(current_setting('app.receipt_hash', true), ''))"
    )
    op.execute(
        "CREATE POLICY deletion_operation_account_lookup ON privacy.deletion_operation "
        "FOR SELECT TO gutcare_app USING (account_hash = "
        "NULLIF(current_setting('app.account_hash', true), ''))"
    )
    op.execute(
        "CREATE POLICY deletion_operation_create ON privacy.deletion_operation "
        "FOR INSERT TO gutcare_app WITH CHECK (account_hash = "
        "NULLIF(current_setting('app.account_hash', true), ''))"
    )
    op.execute(
        "CREATE POLICY deletion_operation_receipt_rotate ON privacy.deletion_operation "
        "FOR UPDATE TO gutcare_app USING (account_hash = "
        "NULLIF(current_setting('app.account_hash', true), '')) WITH CHECK (account_hash = "
        "NULLIF(current_setting('app.account_hash', true), ''))"
    )
    op.execute(
        "CREATE POLICY deletion_step_worker ON privacy.deletion_step TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY object_inventory_worker ON privacy.object_inventory TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY export_operation_owner ON privacy.export_operation USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY export_operation_capability ON privacy.export_operation "
        "TO gutcare_app USING (capability_hash = "
        "NULLIF(current_setting('app.export_capability_hash', true), '')) "
        "WITH CHECK (capability_hash = NULLIF(current_setting('app.export_capability_hash', true), ''))"
    )
    op.execute(
        "CREATE POLICY export_operation_worker ON privacy.export_operation TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY security_audit_worker ON privacy.security_audit TO gutcare_privacy_worker USING (true) WITH CHECK (true)"
    )
    op.execute("GRANT USAGE ON SCHEMA privacy TO gutcare_app, gutcare_privacy_worker")
    op.execute(
        "GRANT USAGE ON SCHEMA iam, health, analysis, safety, integration TO gutcare_privacy_worker"
    )
    op.execute(
        "GRANT SELECT, DELETE ON integration.file_orphan_cleanup_job TO gutcare_privacy_worker"
    )
    op.execute("GRANT SELECT, INSERT ON privacy.deletion_operation TO gutcare_app")
    op.execute("GRANT UPDATE (receipt_hash) ON privacy.deletion_operation TO gutcare_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON privacy.export_operation TO gutcare_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON privacy.deletion_operation, privacy.deletion_step, privacy.object_inventory, privacy.export_operation TO gutcare_privacy_worker"
    )
    op.execute("GRANT INSERT, SELECT, DELETE ON privacy.security_audit TO gutcare_privacy_worker")
    op.execute("""
        DO $$ DECLARE item record; BEGIN
          FOR item IN
            SELECT table_schema, table_name FROM information_schema.columns
            WHERE column_name = 'patient_id' AND table_schema IN ('health','analysis','safety','integration')
          LOOP
            EXECUTE format('GRANT SELECT, UPDATE, DELETE ON %I.%I TO gutcare_privacy_worker', item.table_schema, item.table_name);
            IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname=item.table_schema AND c.relname=item.table_name AND c.relrowsecurity) THEN
              IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=item.table_schema AND tablename=item.table_name AND policyname='privacy_worker_scope') THEN
                EXECUTE format('CREATE POLICY privacy_worker_scope ON %I.%I TO gutcare_privacy_worker USING (patient_id = NULLIF(current_setting(''app.patient_id'', true), '''')::uuid) WITH CHECK (patient_id = NULLIF(current_setting(''app.patient_id'', true), '''')::uuid)', item.table_schema, item.table_name);
              END IF;
            END IF;
          END LOOP;
        END $$;
    """)
    op.execute(
        "GRANT SELECT, UPDATE, DELETE ON iam.user_account, iam.refresh_session, iam.email_verification_token TO gutcare_privacy_worker"
    )
    op.execute("GRANT SELECT, DELETE ON health.patient_profile TO gutcare_privacy_worker")
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='health' AND tablename='patient_profile' AND policyname='privacy_worker_profile_scope') THEN
            CREATE POLICY privacy_worker_profile_scope ON health.patient_profile
            TO gutcare_privacy_worker USING (id = NULLIF(current_setting('app.patient_id', true), '')::uuid);
          END IF;
        END $$;
    """)
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA privacy TO gutcare_app, gutcare_privacy_worker"
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM privacy.deletion_operation)
             OR EXISTS (SELECT 1 FROM privacy.export_operation)
             OR EXISTS (SELECT 1 FROM privacy.security_audit) THEN
            RAISE EXCEPTION 'F13 privacy lifecycle contains durable records and is forward-only';
          END IF;
        END $$;
    """)
    op.execute("""
        DO $$ DECLARE item record; BEGIN
          FOR item IN
            SELECT schemaname, tablename, policyname FROM pg_policies
            WHERE policyname IN ('privacy_worker_scope','privacy_worker_profile_scope')
              AND schemaname IN ('health','analysis','safety','integration')
          LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', item.policyname, item.schemaname, item.tablename);
          END LOOP;
        END $$;
    """)
    op.execute(
        "REVOKE SELECT, UPDATE, DELETE ON ALL TABLES IN SCHEMA health, analysis, safety, integration FROM gutcare_privacy_worker"
    )
    op.execute(
        "REVOKE SELECT, UPDATE, DELETE ON iam.user_account, iam.refresh_session, iam.email_verification_token, health.patient_profile FROM gutcare_privacy_worker"
    )
    op.execute(
        "DROP POLICY IF EXISTS file_orphan_cleanup_existing_worker ON integration.file_orphan_cleanup_job"
    )
    op.execute(
        "DROP POLICY IF EXISTS file_orphan_cleanup_app_insert ON integration.file_orphan_cleanup_job"
    )
    op.execute("ALTER TABLE integration.file_orphan_cleanup_job DISABLE ROW LEVEL SECURITY")
    op.drop_constraint(
        "fk_file_orphan_cleanup_patient",
        "file_orphan_cleanup_job",
        schema="integration",
        type_="foreignkey",
    )
    op.drop_column("file_orphan_cleanup_job", "patient_id", schema="integration")
    op.execute("DROP SCHEMA privacy CASCADE")
