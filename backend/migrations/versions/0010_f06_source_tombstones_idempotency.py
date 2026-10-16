"""Add stable medication source tombstones and idempotent response snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_f06_source_refs"
down_revision: str | None = "0009_f06_medication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medication_source_ref",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("original_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("live_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("source_kind = 'medical_document'", name="ck_med_source_ref_kind"),
        sa.CheckConstraint(
            "(live_document_id IS NULL) = (source_deleted_at IS NOT NULL)",
            name="ck_med_source_ref_tombstone",
        ),
        sa.CheckConstraint(
            "live_document_id IS NULL OR original_document_id = live_document_id",
            name="ck_med_source_ref_original_live",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["live_document_id", "patient_id"],
            ["health.medical_document.id", "health.medical_document.patient_id"],
            ondelete="RESTRICT",
            name="fk_med_source_ref_live_document_patient",
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_med_source_ref_id_patient"),
        sa.UniqueConstraint(
            "patient_id", "original_document_id", name="uq_med_source_ref_patient_original_document"
        ),
        schema="health",
    )
    op.create_table(
        "medication_migration_marker",
        sa.Column("marker_key", sa.String(64), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="health",
    )
    # This migration runs as the non-BYPASSRLS migrator. Temporarily disable
    # forced row policies only while constructing cross-patient backfills.
    for table in (
        "medical_document",
        "medication_plan",
        "medication_schedule",
        "medication_idempotency",
    ):
        op.execute(f"ALTER TABLE health.{table} DISABLE ROW LEVEL SECURITY")
    op.execute("""INSERT INTO health.medication_source_ref
        (patient_id, source_kind, original_document_id, live_document_id, source_deleted_at)
        SELECT DISTINCT ON (p.patient_id, p.source_document_id)
               p.patient_id, 'medical_document', p.source_document_id,
               CASE WHEN d.deleted_at IS NULL THEN d.id ELSE NULL END,
               d.deleted_at
        FROM health.medication_plan p
        JOIN health.medical_document d
          ON d.id = p.source_document_id AND d.patient_id = p.patient_id
        WHERE p.source_type = 'medical_document'
        ORDER BY p.patient_id, p.source_document_id""")
    op.execute("""INSERT INTO health.medication_migration_marker (marker_key)
        SELECT 'f06-source-tombstone-seen'
        WHERE EXISTS (
          SELECT 1 FROM health.medication_source_ref WHERE source_deleted_at IS NOT NULL
        ) ON CONFLICT DO NOTHING""")
    op.add_column(
        "medication_plan",
        sa.Column("source_ref_id", postgresql.UUID(as_uuid=True)),
        schema="health",
    )
    op.execute("""UPDATE health.medication_plan p SET source_ref_id = s.id
        FROM health.medication_source_ref s
        WHERE p.patient_id = s.patient_id AND p.source_document_id = s.original_document_id""")
    op.drop_constraint(
        "fk_med_plan_document_patient", "medication_plan", schema="health", type_="foreignkey"
    )
    op.drop_column("medication_plan", "source_document_id", schema="health")
    op.create_foreign_key(
        "fk_med_plan_source_ref_patient",
        "medication_plan",
        "medication_source_ref",
        ["source_ref_id", "patient_id"],
        ["id", "patient_id"],
        source_schema="health",
        referent_schema="health",
    )
    op.create_check_constraint(
        "ck_med_plan_source_ref",
        "medication_plan",
        "(source_type = 'manual' AND source_ref_id IS NULL) OR "
        "(source_type = 'medical_document' AND source_ref_id IS NOT NULL)",
        schema="health",
    )
    op.add_column(
        "medication_idempotency",
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="health",
    )
    op.add_column(
        "medication_idempotency",
        sa.Column("response_status", sa.Integer(), nullable=True),
        schema="health",
    )
    op.execute("""UPDATE health.medication_idempotency i SET
        response_snapshot = jsonb_build_object(
          'id', p.id::text, 'patient_id', p.patient_id::text, 'medication_name', p.medication_name,
          'dosage_text', p.dosage_text, 'route_code', p.route_code,
          'start_date', p.start_date::text, 'end_date', p.end_date::text,
          'source_type', p.source_type,
          'source_document_id', CASE WHEN s.live_document_id IS NULL
            THEN NULL ELSE s.live_document_id::text END,
          'source_deleted', s.source_deleted_at IS NOT NULL,
          'confirmation_status', p.confirmation_status, 'plan_status', p.plan_status,
          'record_version', p.record_version, 'created_at', p.created_at::text,
          'updated_at', p.updated_at::text),
        response_status = CASE WHEN i.route = 'POST:/medication-plans' THEN 201 ELSE 200 END
        FROM health.medication_plan p LEFT JOIN health.medication_source_ref s
          ON s.id = p.source_ref_id AND s.patient_id = p.patient_id
        WHERE i.resource_id = p.id AND i.patient_id = p.patient_id
          AND (i.route = 'POST:/medication-plans'
               OR i.route LIKE 'POST:/medication-plans/%/transitions')""")
    op.execute("""UPDATE health.medication_idempotency i SET
        response_snapshot = jsonb_build_object(
          'id', s.id::text, 'plan_id', s.plan_id::text, 'local_time', s.local_time::text,
          'timezone', s.timezone, 'rrule', s.rrule,
          'valid_from', s.valid_from::text, 'valid_to', s.valid_to::text,
          'enabled', s.enabled, 'record_version', s.record_version),
        response_status = 201
        FROM health.medication_schedule s
        WHERE i.resource_id = s.id AND i.patient_id = s.patient_id
          AND i.route LIKE 'POST:/medication-plans/%/schedules'""")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM health.medication_idempotency "
        "WHERE response_snapshot IS NULL OR response_status IS NULL) THEN "
        "RAISE EXCEPTION '0010 cannot backfill idempotency route/resource; repair ledger'; "
        "END IF; END $$"
    )
    op.alter_column("medication_idempotency", "response_snapshot", nullable=False, schema="health")
    op.alter_column("medication_idempotency", "response_status", nullable=False, schema="health")
    for table in (
        "medical_document",
        "medication_plan",
        "medication_schedule",
        "medication_idempotency",
    ):
        op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.medication_source_ref ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.medication_source_ref FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY medication_source_ref_patient_isolation "
        "ON health.medication_source_ref "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute("""CREATE FUNCTION health.guard_medication_source_ref()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, health AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.live_document_id IS NULL OR NEW.source_deleted_at IS NOT NULL THEN
              RAISE EXCEPTION 'source references must start live' USING ERRCODE = '23514';
            END IF;
          ELSE
            IF NEW.patient_id <> OLD.patient_id
              OR NEW.source_kind <> OLD.source_kind
              OR NEW.original_document_id <> OLD.original_document_id THEN
              RAISE EXCEPTION 'source reference identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.live_document_id IS NULL OR NEW.live_document_id IS NOT NULL
              OR NEW.source_deleted_at IS NULL THEN
              RAISE EXCEPTION 'source reference may only transition to tombstone'
                USING ERRCODE = '23514';
            END IF;
            INSERT INTO health.medication_migration_marker (marker_key)
            VALUES ('f06-source-tombstone-seen') ON CONFLICT DO NOTHING;
          END IF;
          RETURN NEW;
        END $$""")
    op.execute(
        "CREATE TRIGGER medication_source_ref_guard "
        "BEFORE INSERT OR UPDATE ON health.medication_source_ref "
        "FOR EACH ROW EXECUTE FUNCTION health.guard_medication_source_ref()"
    )
    op.execute(
        "REVOKE ALL ON health.medication_migration_marker FROM PUBLIC, gutcare_app, gutcare_worker"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON health.medication_source_ref TO gutcare_app")
    op.execute("GRANT SELECT, UPDATE ON health.medication_source_ref TO gutcare_worker")
    op.execute(
        "GRANT UPDATE (response_snapshot) ON health.medication_idempotency "
        "TO gutcare_app, gutcare_worker"
    )
    op.execute("GRANT SELECT ON health.medication_idempotency TO gutcare_worker")


def downgrade() -> None:
    # This is deliberately the first database operation: a global marker has
    # no patient/business data and is visible to the non-BYPASSRLS migrator.
    bind = op.get_bind()
    tombstone_seen = bind.scalar(
        sa.text("""SELECT EXISTS (
            SELECT 1 FROM health.medication_migration_marker
            WHERE marker_key = 'f06-source-tombstone-seen'
        )""")
    )
    if tombstone_seen:
        raise RuntimeError(
            "0010 is forward-only after source deletion: tombstone data cannot be "
            "reconstructed as medical_document rows. Keep schema at 0010 or restore "
            "a pre-migration backup before any deletion; do not downgrade this database."
        )
    op.execute(
        "REVOKE UPDATE (response_snapshot) ON health.medication_idempotency "
        "FROM gutcare_app, gutcare_worker"
    )
    op.execute("REVOKE SELECT ON health.medication_idempotency FROM gutcare_worker")
    op.drop_constraint(
        "fk_med_plan_source_ref_patient", "medication_plan", schema="health", type_="foreignkey"
    )
    op.drop_constraint("ck_med_plan_source_ref", "medication_plan", schema="health", type_="check")
    op.add_column(
        "medication_plan",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True)),
        schema="health",
    )
    op.execute("""UPDATE health.medication_plan p
        SET source_document_id = s.original_document_id
        FROM health.medication_source_ref s
        WHERE p.source_ref_id = s.id AND p.patient_id = s.patient_id""")
    op.create_foreign_key(
        "fk_med_plan_document_patient",
        "medication_plan",
        "medical_document",
        ["source_document_id", "patient_id"],
        ["id", "patient_id"],
        source_schema="health",
        referent_schema="health",
    )
    op.drop_column("medication_plan", "source_ref_id", schema="health")
    op.drop_column("medication_idempotency", "response_snapshot", schema="health")
    op.drop_column("medication_idempotency", "response_status", schema="health")
    op.drop_table("medication_migration_marker", schema="health")
    op.execute(
        "DROP POLICY medication_source_ref_patient_isolation ON health.medication_source_ref"
    )
    op.execute("DROP TRIGGER medication_source_ref_guard ON health.medication_source_ref")
    op.execute("DROP FUNCTION health.guard_medication_source_ref()")
    op.drop_table("medication_source_ref", schema="health")
