"""F03/F04 record image attachments and dedicated recognition lifecycle."""
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_f03_f04_recognition"
down_revision: str | None = "0026_h3b_mood_privacy_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "diet_record",
        sa.Column("image_set_version", sa.Integer(), nullable=False, server_default="1"),
        schema="health",
    )
    op.add_column(
        "stool_record",
        sa.Column("image_set_version", sa.Integer(), nullable=False, server_default="1"),
        schema="health",
    )
    op.add_column("diet_item", sa.Column("item_position", sa.Integer()), schema="health")
    op.add_column(
        "diet_item",
        sa.Column("source_recognition_request_id", postgresql.UUID(as_uuid=True)),
        schema="health",
    )
    op.add_column(
        "diet_item",
        sa.Column("source_candidate_group_key", postgresql.UUID(as_uuid=True)),
        schema="health",
    )
    op.execute(
        "UPDATE health.diet_item SET item_position=ranked.position FROM (SELECT id,ROW_NUMBER() OVER (PARTITION BY patient_id,diet_record_id ORDER BY id)-1 AS position FROM health.diet_item) ranked WHERE health.diet_item.id=ranked.id"
    )
    op.alter_column("diet_item", "item_position", nullable=False, schema="health")
    op.create_unique_constraint(
        "uq_diet_item_position_patient_record",
        "diet_item",
        ["patient_id", "diet_record_id", "item_position"],
        schema="health",
    )
    op.create_check_constraint(
        "ck_diet_item_image_position_nonnegative",
        "diet_item",
        "item_position >= 0",
        schema="health",
    )
    op.create_check_constraint(
        "ck_diet_item_image_source_pair",
        "diet_item",
        "(source_recognition_request_id IS NULL AND source_candidate_group_key IS NULL) OR (source_recognition_request_id IS NOT NULL AND source_candidate_group_key IS NOT NULL)",
        schema="health",
    )
    for table, record in (
        ("diet_record_image", "diet_record"),
        ("stool_record_image", "stool_record"),
    ):
        op.create_table(
            table,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuidv7()"),
            ),
            sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("file_object_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("position", sa.SmallInteger(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("id", "patient_id", name=f"uq_{table}_id_patient"),
            sa.UniqueConstraint("file_object_id", "patient_id", name=f"uq_{table}_file_patient"),
            sa.ForeignKeyConstraint(
                ["record_id", "patient_id"],
                [f"health.{record}.id", f"health.{record}.patient_id"],
                name=f"fk_{table}_record_patient",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["file_object_id", "patient_id"],
                ["health.file_object.id", "health.file_object.patient_id"],
                name=f"fk_{table}_file_patient",
            ),
            sa.CheckConstraint(
                "position BETWEEN 0 AND 9" if table.startswith("diet") else "position = 0",
                name=f"ck_{table}_position",
            ),
            schema="health",
        )
        op.create_index(
            f"uq_{table}_active_record_position",
            table,
            ["patient_id", "record_id", "position"],
            unique=True,
            schema="health",
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_patient ON health.{table} FOR ALL TO gutcare_app USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
        op.execute(
            f"CREATE POLICY {table}_privacy_worker ON health.{table} FOR ALL TO gutcare_privacy_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
        op.execute(
            f"CREATE POLICY {table}_file_worker_select ON health.{table} FOR SELECT TO gutcare_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
        op.execute(
            f"CREATE POLICY {table}_file_worker_delete ON health.{table} FOR DELETE TO gutcare_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
        op.execute(
            f"CREATE POLICY {table}_analysis_worker_select ON health.{table} FOR SELECT TO gutcare_analysis_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
    op.create_index(
        "uq_stool_record_image_active",
        "stool_record_image",
        ["patient_id", "record_id"],
        unique=True,
        schema="health",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute("""
        CREATE FUNCTION health.check_record_image_file() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected_purpose text; actual_purpose text; scan text; storage text;
        BEGIN
          expected_purpose := CASE WHEN TG_TABLE_NAME='diet_record_image' THEN 'diet_image' ELSE 'stool_image' END;
          SELECT u.purpose,f.scan_status,f.storage_status INTO actual_purpose,scan,storage
            FROM health.upload_session u JOIN health.file_object f
              ON f.id=u.file_object_id AND f.patient_id=u.patient_id
            WHERE u.file_object_id=NEW.file_object_id AND u.patient_id=NEW.patient_id
              AND u.status='completed';
          IF current_setting('app.record_image_backfill',true) IS DISTINCT FROM 'on' AND
             (actual_purpose IS DISTINCT FROM expected_purpose OR scan IS DISTINCT FROM 'clean' OR storage IS DISTINCT FROM 'available') THEN
            RAISE EXCEPTION 'record image file unavailable' USING ERRCODE='23514';
          END IF;
          IF TG_TABLE_NAME='diet_record_image' AND EXISTS (SELECT 1 FROM health.stool_record_image WHERE file_object_id=NEW.file_object_id AND patient_id=NEW.patient_id)
             OR TG_TABLE_NAME='stool_record_image' AND EXISTS (SELECT 1 FROM health.diet_record_image WHERE file_object_id=NEW.file_object_id AND patient_id=NEW.patient_id) THEN
            RAISE EXCEPTION 'record image already attached' USING ERRCODE='23505';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER diet_record_image_file BEFORE INSERT OR UPDATE OF file_object_id,patient_id ON health.diet_record_image FOR EACH ROW EXECUTE FUNCTION health.check_record_image_file();
        CREATE TRIGGER stool_record_image_file BEFORE INSERT OR UPDATE OF file_object_id,patient_id ON health.stool_record_image FOR EACH ROW EXECUTE FUNCTION health.check_record_image_file();
    """)
    op.execute("ALTER TABLE health.diet_record_image DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.stool_record_image DISABLE ROW LEVEL SECURITY")
    op.execute("SET LOCAL app.record_image_backfill = 'on'")
    op.execute("""
        INSERT INTO health.diet_record_image (patient_id, record_id, file_object_id, position)
        SELECT patient_id, id, image_object_id, 0 FROM health.diet_record WHERE image_object_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO health.stool_record_image (patient_id, record_id, file_object_id, position)
        SELECT patient_id, id, image_object_id, 0 FROM health.stool_record WHERE image_object_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    op.execute("ALTER TABLE health.diet_record_image ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.diet_record_image FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.stool_record_image ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.stool_record_image FORCE ROW LEVEL SECURITY")
    # Keep the legacy nullable columns as a read-compatibility bridge. New writes
    # use attachment rows only; backfilled relations are the canonical source.

    op.create_table(
        "record_image_disclosure",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("image_set_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("summary_sha256", sa.CHAR(64), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "purpose IN ('diet_image_recognition','stool_image_recognition')",
            name="ck_record_image_disclosure_purpose",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_record_image_disclosure_id_patient"),
        schema="health",
    )
    op.create_table(
        "record_image_recognition_request",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disclosure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recognition_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("decision_record_version", sa.Integer(), nullable=False),
        sa.Column("image_set_version", sa.Integer(), nullable=False),
        sa.Column("retry_of_request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(48)),
        sa.Column("callback_id", postgresql.UUID(as_uuid=True)),
        sa.Column("callback_hash", sa.CHAR(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_record_image_request_id_patient"),
        sa.ForeignKeyConstraint(
            ["disclosure_id", "patient_id"],
            ["health.record_image_disclosure.id", "health.record_image_disclosure.patient_id"],
            name="fk_record_image_request_disclosure_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["record_id", "patient_id"],
            ["health.diet_record.id", "health.diet_record.patient_id"],
            name="fk_record_image_request_diet_patient",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            name="fk_record_image_request_retry_parent_patient",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_record_image_request_attempt_retry"),
        sa.CheckConstraint(
            "recognition_type IN ('diet_image_recognition','stool_image_recognition')",
            name="ck_record_image_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','candidates_ready','no_candidates','failed','cancelled','invalidated')",
            name="ck_record_image_request_status",
        ),
        schema="analysis",
    )
    op.create_index(
        "uq_record_image_request_retry_parent",
        "record_image_recognition_request",
        ["retry_of_request_id"],
        unique=True,
        schema="analysis",
        postgresql_where=sa.text("retry_of_request_id IS NOT NULL"),
    )
    op.create_table(
        "record_image_request_attachment",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("file_version", sa.Integer(), nullable=False),
        sa.Column("diet_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("stool_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint(
            "request_id", "position", name="pk_record_image_request_attachment"
        ),
        sa.UniqueConstraint(
            "request_id",
            "diet_attachment_id",
            name="uq_record_image_request_attachment_diet_per_request",
        ),
        sa.UniqueConstraint(
            "request_id",
            "stool_attachment_id",
            name="uq_record_image_request_attachment_stool_per_request",
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            name="fk_record_image_request_attachment_request_patient",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diet_attachment_id", "patient_id"],
            ["health.diet_record_image.id", "health.diet_record_image.patient_id"],
            name="fk_record_image_request_attachment_diet_patient",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["stool_attachment_id", "patient_id"],
            ["health.stool_record_image.id", "health.stool_record_image.patient_id"],
            name="fk_record_image_request_attachment_stool_patient",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(diet_attachment_id IS NOT NULL) <> (stool_attachment_id IS NOT NULL)",
            name="ck_record_image_request_attachment_xor",
        ),
        sa.CheckConstraint("position >= 0", name="ck_record_image_request_attachment_position"),
        sa.CheckConstraint("file_version = 1", name="ck_record_image_request_attachment_version"),
        schema="analysis",
    )
    op.execute("""
        CREATE FUNCTION analysis.check_record_image_request_attachment_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE kind text; source_record uuid; attachment_record uuid;
        BEGIN
          SELECT recognition_type,r.record_id INTO kind,source_record
            FROM analysis.record_image_recognition_request r
           WHERE r.id=NEW.request_id AND r.patient_id=NEW.patient_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'record image request missing' USING ERRCODE='23503';
          END IF;
          IF (kind='diet_image_recognition' AND NEW.diet_attachment_id IS NULL)
             OR (kind='stool_image_recognition' AND NEW.stool_attachment_id IS NULL) THEN
            RAISE EXCEPTION 'record image attachment type mismatch' USING ERRCODE='23514';
          END IF;
          IF NEW.diet_attachment_id IS NOT NULL THEN
            SELECT a.record_id INTO attachment_record FROM health.diet_record_image a
             WHERE a.id=NEW.diet_attachment_id AND a.patient_id=NEW.patient_id;
          ELSE
            SELECT a.record_id INTO attachment_record FROM health.stool_record_image a
             WHERE a.id=NEW.stool_attachment_id AND a.patient_id=NEW.patient_id;
          END IF;
          IF attachment_record IS DISTINCT FROM source_record THEN
            RAISE EXCEPTION 'record image attachment source mismatch' USING ERRCODE='23503';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER record_image_request_attachment_scope
        BEFORE INSERT OR UPDATE OF request_id,patient_id,diet_attachment_id,stool_attachment_id
        ON analysis.record_image_request_attachment FOR EACH ROW
        EXECUTE FUNCTION analysis.check_record_image_request_attachment_scope();
    """)
    op.create_table(
        "record_image_capability",
        sa.Column("capability_hash", sa.CHAR(64), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("file_version >= 1", name="ck_record_image_capability_file_version"),
        schema="analysis",
    )
    op.create_index(
        "ix_record_image_capability_expiry",
        "record_image_capability",
        ["expires_at"],
        schema="analysis",
    )
    op.create_table(
        "record_image_dispatch_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(32)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "request_id", "attempt", name="uq_record_image_dispatch_request_attempt"
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "attempt >= 1 AND attempts >= 0", name="ck_record_image_dispatch_attempts"
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','dispatched','dead_letter')",
            name="ck_record_image_dispatch_status",
        ),
        schema="analysis",
    )
    op.create_index(
        "ix_record_image_dispatch_ready",
        "record_image_dispatch_outbox",
        ["status", "available_at", "created_at"],
        schema="analysis",
    )
    # Use a trigger for record ownership across the two record tables while retaining a single request table.
    op.execute("""
        ALTER TABLE analysis.record_image_recognition_request DROP CONSTRAINT fk_record_image_request_diet_patient;
        CREATE FUNCTION analysis.check_record_image_request_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (NEW.recognition_type = 'diet_image_recognition' AND NOT EXISTS (SELECT 1 FROM health.diet_record WHERE id=NEW.record_id AND patient_id=NEW.patient_id)) OR
             (NEW.recognition_type = 'stool_image_recognition' AND NOT EXISTS (SELECT 1 FROM health.stool_record WHERE id=NEW.record_id AND patient_id=NEW.patient_id)) THEN
            RAISE EXCEPTION 'record image request ownership mismatch' USING ERRCODE='23503';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER record_image_request_owner BEFORE INSERT OR UPDATE OF record_id, patient_id, recognition_type ON analysis.record_image_recognition_request FOR EACH ROW EXECUTE FUNCTION analysis.check_record_image_request_owner();
    """)
    op.create_index(
        "ix_record_image_request_pending",
        "record_image_recognition_request",
        ["status", "created_at"],
        schema="analysis",
        postgresql_where=sa.text("status IN ('pending','processing')"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_record_image_request_active_record ON analysis.record_image_recognition_request(patient_id, record_id) WHERE status IN ('pending','processing','candidates_ready')"
    )
    op.create_table(
        "record_image_candidate",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_type", sa.String(32), nullable=False),
        sa.Column("candidate_group_key", postgresql.UUID(as_uuid=True)),
        sa.Column("confidence_band", sa.String(8), nullable=False),
        sa.Column("source_state", sa.String(24), nullable=False, server_default="current"),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("locator", postgresql.JSONB()),
        sa.Column("uncertainty", sa.String(24), nullable=False),
        sa.Column("candidate_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','edited','rejected','invalidated')",
            name="ck_record_image_candidate_status",
        ),
        sa.CheckConstraint(
            "confidence_band IN ('low','medium','high')",
            name="ck_record_image_candidate_confidence",
        ),
        sa.CheckConstraint(
            "uncertainty IN ('partially_occluded','mixed_food','low_light','ambiguous_shape','image_quality','other')",
            name="ck_record_image_candidate_uncertainty",
        ),
        sa.CheckConstraint(
            "candidate_type IN ('food_name','food_category','portion_description','bristol_type') AND CASE WHEN status<>'pending' THEN value='null'::jsonb AND locator IS NULL ELSE CASE WHEN candidate_type='bristol_type' THEN candidate_group_key IS NULL AND jsonb_typeof(value)='number' AND (value #>> '{}')::integer BETWEEN 1 AND 7 ELSE candidate_group_key IS NOT NULL AND jsonb_typeof(value)='string' AND length(value #>> '{}') BETWEEN 1 AND 160 END END",
            name="ck_record_image_candidate_type_value_group",
        ),
        sa.CheckConstraint(
            "candidate_type <> 'food_category' OR status<>'pending' OR value #>> '{}' IN ('grain_staple','vegetable','fruit','meat','seafood','dairy','egg','legume','snack','beverage','mixed_dish','other')",
            name="ck_record_image_candidate_category_value",
        ),
        schema="analysis",
    )
    op.execute("ALTER TABLE analysis.record_image_request_attachment ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE analysis.record_image_request_attachment FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY record_image_request_attachment_migrator
        ON analysis.record_image_request_attachment FOR ALL TO gutcare_migrator
        USING (true) WITH CHECK (true)
    """)
    op.execute("""
        CREATE POLICY record_image_request_attachment_patient
        ON analysis.record_image_request_attachment FOR ALL TO gutcare_app
        USING (patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid)
        WITH CHECK (patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid)
    """)
    op.execute("""
        CREATE POLICY record_image_request_attachment_worker
        ON analysis.record_image_request_attachment FOR SELECT TO gutcare_analysis_worker
        USING (true)
    """)
    op.execute("""
        CREATE POLICY record_image_request_attachment_privacy_worker
        ON analysis.record_image_request_attachment FOR ALL TO gutcare_privacy_worker
        USING (patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid)
        WITH CHECK (patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid)
    """)
    op.execute("""
        GRANT SELECT,INSERT,DELETE ON analysis.record_image_request_attachment TO gutcare_app;
        GRANT SELECT ON analysis.record_image_request_attachment TO gutcare_analysis_worker;
        GRANT SELECT,DELETE ON analysis.record_image_request_attachment TO gutcare_privacy_worker;
    """)
    op.execute("""
        CREATE POLICY record_image_request_migrator
        ON analysis.record_image_recognition_request FOR SELECT TO gutcare_migrator
        USING (true)
    """)
    op.execute("""
        CREATE FUNCTION analysis.check_record_image_candidate_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE kind text; rid uuid;
        BEGIN
          SELECT recognition_type,record_id INTO kind,rid FROM analysis.record_image_recognition_request
            WHERE id=NEW.request_id AND patient_id=NEW.patient_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'record image request missing' USING ERRCODE='23503'; END IF;
          IF (kind='diet_image_recognition' AND (NEW.candidate_type NOT IN ('food_name','food_category','portion_description') OR NEW.candidate_group_key IS NULL)) OR
             (kind='stool_image_recognition' AND (NEW.candidate_type<>'bristol_type' OR NEW.candidate_group_key IS NOT NULL)) THEN
            RAISE EXCEPTION 'record image candidate type mismatch' USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM analysis.record_image_request_attachment a
             WHERE a.request_id=NEW.request_id AND a.patient_id=NEW.patient_id
               AND ((kind='diet_image_recognition' AND a.diet_attachment_id=NEW.attachment_id)
                 OR (kind='stool_image_recognition' AND a.stool_attachment_id=NEW.attachment_id))
          ) THEN
            RAISE EXCEPTION 'record image candidate attachment mismatch' USING ERRCODE='23503';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER record_image_candidate_scope BEFORE INSERT OR UPDATE OF request_id,patient_id,attachment_id,candidate_type,candidate_group_key ON analysis.record_image_candidate FOR EACH ROW EXECUTE FUNCTION analysis.check_record_image_candidate_scope();
    """)
    op.create_foreign_key(
        "fk_diet_item_recognition_source_patient",
        "diet_item",
        "record_image_recognition_request",
        ["source_recognition_request_id", "patient_id"],
        ["id", "patient_id"],
        source_schema="health",
        referent_schema="analysis",
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_diet_item_recognition_group",
        "diet_item",
        [
            "patient_id",
            "diet_record_id",
            "source_recognition_request_id",
            "source_candidate_group_key",
        ],
        unique=True,
        schema="health",
        postgresql_where=sa.text("source_recognition_request_id IS NOT NULL"),
    )
    op.create_index(
        "uq_record_image_candidate_group_type",
        "record_image_candidate",
        ["request_id", "candidate_group_key", "candidate_type"],
        unique=True,
        schema="analysis",
        postgresql_where=sa.text("candidate_group_key IS NOT NULL"),
    )
    op.create_index(
        "uq_record_image_stool_candidate_type",
        "record_image_candidate",
        ["request_id", "candidate_type"],
        unique=True,
        schema="analysis",
        postgresql_where=sa.text("candidate_group_key IS NULL"),
    )
    op.create_index(
        "ix_record_image_candidate_request",
        "record_image_candidate",
        ["patient_id", "request_id", "status"],
        schema="analysis",
    )
    op.create_table(
        "record_image_decision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("candidate_type", sa.String(32), nullable=False),
        sa.Column("source_state", sa.String(24), nullable=False, server_default="current"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('accept','edit','reject')", name="ck_record_image_decision_action"
        ),
        sa.CheckConstraint(
            "source_state IN ('current','source_deleted')",
            name="ck_record_image_decision_source_state",
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "patient_id"],
            [
                "analysis.record_image_recognition_request.id",
                "analysis.record_image_recognition_request.patient_id",
            ],
            ondelete="CASCADE",
        ),
        schema="analysis",
    )
    op.create_table(
        "record_image_idempotency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(48), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="health",
    )
    op.execute("""
        CREATE UNIQUE INDEX uq_record_image_idempotency_scope_key
        ON health.record_image_idempotency(
          patient_id,operation,
          COALESCE(scope_id,'00000000-0000-0000-0000-000000000000'::uuid),
          idempotency_key
        )
    """)
    for schema, table, _cols in (
        ("analysis", "record_image_recognition_request", "patient_id, record_id"),
        ("analysis", "record_image_capability", "patient_id"),
        ("analysis", "record_image_dispatch_outbox", "patient_id"),
        ("analysis", "record_image_candidate", "patient_id"),
        ("analysis", "record_image_decision", "patient_id"),
        ("health", "record_image_disclosure", "patient_id, record_id"),
        ("health", "record_image_idempotency", "patient_id"),
    ):
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {schema}.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_patient ON {schema}.{table} FOR ALL TO gutcare_app USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
        if schema == "analysis":
            op.execute(
                f"CREATE POLICY {table}_worker ON {schema}.{table} FOR ALL TO gutcare_analysis_worker USING (true) WITH CHECK (true)"
            )
            op.execute(
                f"CREATE POLICY {table}_privacy_worker ON {schema}.{table} FOR ALL TO gutcare_privacy_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
            )
        elif table in {"record_image_disclosure", "record_image_idempotency"}:
            op.execute(
                f"CREATE POLICY {table}_privacy_worker ON {schema}.{table} FOR ALL TO gutcare_privacy_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
            )
            if table == "record_image_disclosure":
                op.execute(
                    "CREATE POLICY record_image_disclosure_analysis_worker ON health.record_image_disclosure FOR SELECT TO gutcare_analysis_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
                )
    op.execute("GRANT USAGE ON SCHEMA analysis TO gutcare_app, gutcare_analysis_worker")
    op.execute("GRANT USAGE ON SCHEMA analysis TO gutcare_privacy_worker")
    op.execute("GRANT USAGE ON SCHEMA health TO gutcare_analysis_worker")
    op.execute(
        "CREATE POLICY file_object_dispatch_function_select ON health.file_object FOR SELECT TO gutcare_migrator USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    for attachment_table in ("diet_record_image", "stool_record_image"):
        op.execute(
            f"CREATE POLICY {attachment_table}_dispatch_function_select ON health.{attachment_table} FOR SELECT TO gutcare_migrator USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
        )
    op.execute("""
        CREATE FUNCTION analysis.list_record_image_worker_attachments(p_patient_id uuid,p_record_id uuid,p_recognition_type text)
        RETURNS TABLE(attachment_id uuid,file_object_id uuid,file_version integer,attachment_position integer,content_type text,bucket_name text,object_key text,storage_status text,scan_status text)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,health AS $$
          SELECT a.id,a.file_object_id,1,a.position,f.content_type,f.bucket_name,f.object_key,f.storage_status,f.scan_status
            FROM health.diet_record_image a JOIN health.file_object f ON f.id=a.file_object_id AND f.patient_id=a.patient_id
           WHERE p_recognition_type='diet_image_recognition' AND a.patient_id=p_patient_id
             AND a.record_id=p_record_id AND a.deleted_at IS NULL
             AND p_patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid
          UNION ALL
          SELECT a.id,a.file_object_id,1,a.position,f.content_type,f.bucket_name,f.object_key,f.storage_status,f.scan_status
            FROM health.stool_record_image a JOIN health.file_object f ON f.id=a.file_object_id AND f.patient_id=a.patient_id
           WHERE p_recognition_type='stool_image_recognition' AND a.patient_id=p_patient_id
             AND a.record_id=p_record_id AND a.deleted_at IS NULL
             AND p_patient_id=NULLIF(current_setting('app.patient_id',true),'')::uuid
           ORDER BY 4,1
        $$
    """)
    op.execute(
        "GRANT EXECUTE ON FUNCTION analysis.list_record_image_worker_attachments(uuid,uuid,text) TO gutcare_analysis_worker"
    )
    op.execute("""
        CREATE FUNCTION analysis.get_record_image_worker_context(p_patient_id uuid,p_record_id uuid,p_recognition_type text)
        RETURNS TABLE(record_version integer,image_set_version integer,occurred_at timestamptz,meal_type text,bristol_type smallint)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,health AS $$
        BEGIN
          IF p_patient_id IS DISTINCT FROM NULLIF(current_setting('app.patient_id',true),'')::uuid THEN
            RETURN;
          END IF;
          IF p_recognition_type='diet_image_recognition' THEN
            RETURN QUERY SELECT d.record_version,d.image_set_version,d.occurred_at,d.meal_type::text,NULL::smallint
              FROM health.diet_record d WHERE d.id=p_record_id AND d.patient_id=p_patient_id AND d.deleted_at IS NULL FOR SHARE;
          ELSIF p_recognition_type='stool_image_recognition' THEN
            RETURN QUERY SELECT s.record_version,s.image_set_version,s.occurred_at,NULL::text,s.bristol_type
              FROM health.stool_record s WHERE s.id=p_record_id AND s.patient_id=p_patient_id AND s.deleted_at IS NULL FOR SHARE;
          END IF;
        END $$
    """)
    op.execute(
        "GRANT EXECUTE ON FUNCTION analysis.get_record_image_worker_context(uuid,uuid,text) TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT SELECT ON health.diet_record_image, health.stool_record_image, health.record_image_disclosure TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON analysis.record_image_recognition_request, analysis.record_image_candidate, analysis.record_image_decision TO gutcare_app"
    )
    op.execute("GRANT SELECT, DELETE ON analysis.record_image_capability TO gutcare_app")
    op.execute(
        "GRANT SELECT, UPDATE ON analysis.record_image_recognition_request TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON analysis.record_image_dispatch_outbox TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON analysis.record_image_capability TO gutcare_analysis_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON analysis.record_image_candidate TO gutcare_analysis_worker"
    )
    op.execute("GRANT SELECT, INSERT ON analysis.record_image_decision TO gutcare_app")
    op.execute(
        "GRANT SELECT, DELETE ON analysis.record_image_recognition_request, analysis.record_image_candidate, analysis.record_image_decision, analysis.record_image_dispatch_outbox TO gutcare_privacy_worker"
    )
    op.execute("GRANT SELECT, DELETE ON analysis.record_image_capability TO gutcare_privacy_worker")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON health.diet_record_image, health.stool_record_image, health.record_image_disclosure, health.record_image_idempotency TO gutcare_app"
    )
    op.execute(
        "GRANT SELECT, DELETE ON health.record_image_disclosure, health.record_image_idempotency TO gutcare_privacy_worker"
    )
    op.execute(
        "GRANT SELECT, DELETE ON health.diet_record_image, health.stool_record_image TO gutcare_worker"
    )
    op.execute(
        "GRANT SELECT, DELETE ON health.diet_record_image, health.stool_record_image TO gutcare_privacy_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON health.diet_record, health.stool_record TO gutcare_app"
    )


def downgrade() -> None:
    bind = op.get_bind()
    non_legacy = bind.scalar(
        sa.text("""
        SELECT EXISTS (
          SELECT 1 FROM health.diet_record_image a JOIN health.diet_record r ON r.id=a.record_id AND r.patient_id=a.patient_id
          WHERE a.file_object_id IS DISTINCT FROM r.image_object_id
          UNION ALL
          SELECT 1 FROM health.stool_record_image a JOIN health.stool_record r ON r.id=a.record_id AND r.patient_id=a.patient_id
          WHERE a.file_object_id IS DISTINCT FROM r.image_object_id
        )
    """)
    )
    recognized_data = bind.scalar(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM analysis.record_image_recognition_request)
          OR EXISTS (SELECT 1 FROM health.diet_item WHERE source_recognition_request_id IS NOT NULL)
    """)
    )
    if non_legacy or recognized_data:
        raise RuntimeError(
            "Cannot downgrade 0027 while non-legacy image attachments or recognition data exist"
        )
    op.execute("DROP FUNCTION analysis.list_record_image_worker_attachments(uuid,uuid,text)")
    op.execute("DROP FUNCTION analysis.get_record_image_worker_context(uuid,uuid,text)")
    op.execute("DROP POLICY file_object_dispatch_function_select ON health.file_object")
    op.execute("DROP POLICY diet_record_image_dispatch_function_select ON health.diet_record_image")
    op.execute(
        "DROP POLICY stool_record_image_dispatch_function_select ON health.stool_record_image"
    )
    op.execute(
        "REVOKE SELECT ON health.diet_record_image, health.stool_record_image, health.record_image_disclosure FROM gutcare_analysis_worker"
    )
    op.execute(
        "REVOKE SELECT, DELETE ON health.diet_record_image, health.stool_record_image FROM gutcare_worker, gutcare_privacy_worker"
    )
    for table in ("diet_record_image", "stool_record_image"):
        op.execute(f"ALTER TABLE health.{table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER record_image_request_owner ON analysis.record_image_recognition_request"
    )
    op.execute("DROP FUNCTION analysis.check_record_image_request_owner()")
    op.execute("DROP TRIGGER record_image_candidate_scope ON analysis.record_image_candidate")
    op.execute("DROP FUNCTION analysis.check_record_image_candidate_scope()")
    op.execute(
        "DROP TRIGGER record_image_request_attachment_scope ON analysis.record_image_request_attachment"
    )
    op.execute("DROP FUNCTION analysis.check_record_image_request_attachment_scope()")
    op.drop_constraint(
        "fk_diet_item_recognition_source_patient", "diet_item", schema="health", type_="foreignkey"
    )
    op.drop_index(
        "uq_record_image_idempotency_scope_key",
        table_name="record_image_idempotency",
        schema="health",
    )
    op.drop_table("record_image_idempotency", schema="health")
    for table in (
        "record_image_decision",
        "record_image_candidate",
        "record_image_capability",
        "record_image_dispatch_outbox",
        "record_image_request_attachment",
        "record_image_recognition_request",
    ):
        op.drop_table(table, schema="analysis")
    op.drop_table("record_image_disclosure", schema="health")
    op.execute("DROP TRIGGER diet_record_image_file ON health.diet_record_image")
    op.execute("DROP TRIGGER stool_record_image_file ON health.stool_record_image")
    op.execute("DROP FUNCTION health.check_record_image_file()")
    for table in ("diet_record_image", "stool_record_image"):
        op.drop_table(table, schema="health")
    op.drop_column("diet_record", "image_set_version", schema="health")
    op.drop_column("stool_record", "image_set_version", schema="health")
    op.drop_index("uq_diet_item_recognition_group", table_name="diet_item", schema="health")
    op.drop_constraint(
        "ck_diet_item_image_source_pair", "diet_item", schema="health", type_="check"
    )
    op.drop_constraint(
        "uq_diet_item_position_patient_record", "diet_item", schema="health", type_="unique"
    )
    op.drop_constraint(
        "ck_diet_item_image_position_nonnegative", "diet_item", schema="health", type_="check"
    )
    op.drop_column("diet_item", "source_candidate_group_key", schema="health")
    op.drop_column("diet_item", "source_recognition_request_id", schema="health")
    op.drop_column("diet_item", "item_position", schema="health")
