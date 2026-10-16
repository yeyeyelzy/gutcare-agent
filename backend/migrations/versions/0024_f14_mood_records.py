"""Add patient-owned F14 mood records and consent types."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_f14_mood_records"
down_revision: str | None = "0023_f02_conflict_group_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_patient_consent_type", "patient_consent", schema="health")
    op.create_check_constraint(
        "ck_patient_consent_type",
        "patient_consent",
        "consent_type IN ('privacy_policy','health_data_processing','mood_data_processing',"
        "'mood_ai_sharing','sensitive_image','third_party_ai','push_notification')",
        schema="health",
    )
    op.execute("""
        CREATE FUNCTION health.is_valid_mood_emotion_tags(value jsonb)
        RETURNS boolean LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
        SET search_path = pg_catalog AS $$
        DECLARE item jsonb; tag text; seen text[] := ARRAY[]::text[];
        BEGIN
          IF jsonb_typeof(value) <> 'array' THEN
            RETURN false;
          END IF;
          IF jsonb_array_length(value) > 5 THEN RETURN false; END IF;
          FOR item IN SELECT element FROM jsonb_array_elements(value) AS items(element) LOOP
            IF jsonb_typeof(item) <> 'string' THEN RETURN false; END IF;
            tag := item #>> '{}';
            IF tag NOT IN (
              'calm','content','joyful','sad','anxious','irritable',
              'overwhelmed','tired','other'
            )
               OR tag = ANY(seen) THEN RETURN false; END IF;
            seen := array_append(seen, tag);
          END LOOP;
          RETURN true;
        END $$
    """)
    op.execute("ALTER FUNCTION health.is_valid_mood_emotion_tags(jsonb) OWNER TO gutcare_migrator")
    op.execute("REVOKE ALL ON FUNCTION health.is_valid_mood_emotion_tags(jsonb) FROM PUBLIC")
    op.execute("""
        GRANT EXECUTE ON FUNCTION health.is_valid_mood_emotion_tags(jsonb)
        TO gutcare_app, gutcare_migrator, gutcare_privacy_worker
    """)
    op.create_table(
        "mood_record",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mood_level", sa.SmallInteger(), nullable=False),
        sa.Column(
            "emotion_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("note", sa.String(500)),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("mood_level BETWEEN 1 AND 5", name="ck_mood_record_level"),
        sa.CheckConstraint("record_version >= 1", name="ck_mood_record_version"),
        sa.CheckConstraint(
            "health.is_valid_mood_emotion_tags(emotion_tags)", name="ck_mood_record_emotion_tags"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "patient_id", name="uq_mood_record_id_patient"),
        schema="health",
    )
    op.create_index(
        "ix_mood_record_patient_occurred_active",
        "mood_record",
        ["patient_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
        schema="health",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute("ALTER TABLE health.mood_record ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.mood_record FORCE ROW LEVEL SECURITY")
    op.execute("""
      CREATE POLICY mood_record_patient_select ON health.mood_record FOR SELECT
      USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("""
      CREATE POLICY mood_record_patient_write ON health.mood_record FOR ALL
      USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
      WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("""
      CREATE POLICY mood_record_privacy_worker ON health.mood_record
      FOR ALL TO gutcare_privacy_worker USING (true) WITH CHECK (true)
    """)
    op.execute("GRANT SELECT, INSERT ON health.mood_record TO gutcare_app")
    op.execute("""
        GRANT UPDATE (occurred_at, mood_level, emotion_tags, note, record_version,
                      updated_at, deleted_at) ON health.mood_record TO gutcare_app
    """)
    op.execute("GRANT SELECT, UPDATE, DELETE ON health.mood_record TO gutcare_privacy_worker")
    op.execute("""
        REVOKE ALL ON health.mood_record FROM PUBLIC, gutcare_worker,
        gutcare_analysis_worker, gutcare_notification_worker
    """)


def downgrade() -> None:
    bind = op.get_bind()
    # The migration role is intentionally not BYPASSRLS. Temporarily disable
    # forced RLS transaction-locally so this global safety check cannot miss
    # another patient's retained consent history or mood records. Any refusal
    # rolls back this DDL together with the check; no patient data is altered.
    op.execute("ALTER TABLE health.patient_consent DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.mood_record DISABLE ROW LEVEL SECURITY")
    has_mood_consent = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM health.patient_consent "
            "WHERE consent_type IN ('mood_data_processing', 'mood_ai_sharing'))"
        )
    )
    has_mood_records = bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM health.mood_record)"))
    op.execute("ALTER TABLE health.mood_record ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.patient_consent ENABLE ROW LEVEL SECURITY")
    if has_mood_consent or has_mood_records:
        raise RuntimeError(
            "Cannot downgrade 0024_f14_mood_records while mood_data_processing or "
            "mood_ai_sharing consent history or health.mood_record data exists; "
            "preserve the data and use an explicitly approved migration before downgrade."
        )
    op.drop_table("mood_record", schema="health")
    op.execute("DROP FUNCTION health.is_valid_mood_emotion_tags(jsonb)")
    op.drop_constraint("ck_patient_consent_type", "patient_consent", schema="health")
    op.create_check_constraint(
        "ck_patient_consent_type",
        "patient_consent",
        "consent_type IN ('privacy_policy','health_data_processing',"
        "'sensitive_image','third_party_ai','push_notification')",
        schema="health",
    )
