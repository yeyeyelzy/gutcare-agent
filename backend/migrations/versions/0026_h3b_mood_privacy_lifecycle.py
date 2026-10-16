"""Add replayable seven-day mood record purge queue for F13."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_h3b_mood_privacy_lifecycle"
down_revision: str | None = "0025_f14_analysis_mood"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_export_operation_categories", "export_operation", schema="privacy")
    op.create_check_constraint(
        "ck_export_operation_categories",
        "export_operation",
        "categories <@ ARRAY['profile','consents','medical_documents','files','diet','stool',"
        "'symptoms','medication','activity','mood','analysis','advice','alerts','notifications']::varchar[]",
        schema="privacy",
    )
    op.create_table(
        "mood_purge_queue",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mood_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("patient_id", "mood_record_id", name="pk_mood_purge_queue"),
        sa.ForeignKeyConstraint(
            ["mood_record_id", "patient_id"],
            ["health.mood_record.id", "health.mood_record.patient_id"],
            name="fk_mood_purge_queue_record_patient",
            ondelete="CASCADE",
        ),
        schema="privacy",
    )
    op.create_index(
        "ix_mood_purge_queue_due", "mood_purge_queue", ["purge_after"], schema="privacy"
    )
    op.execute("ALTER TABLE privacy.mood_purge_queue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy.mood_purge_queue FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY mood_purge_queue_patient ON privacy.mood_purge_queue
        FOR ALL TO gutcare_app
        USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
        WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY mood_purge_queue_worker_select ON privacy.mood_purge_queue
        FOR SELECT TO gutcare_privacy_worker USING (true)
    """)
    op.execute("""
        CREATE POLICY mood_purge_queue_worker_delete ON privacy.mood_purge_queue
        FOR DELETE TO gutcare_privacy_worker USING (true)
    """)
    op.execute("GRANT SELECT, INSERT ON privacy.mood_purge_queue TO gutcare_app")
    op.execute("GRANT SELECT, DELETE ON privacy.mood_purge_queue TO gutcare_privacy_worker")

    # Preserve the worker's patient-scoped deletion boundary for the new table
    # introduced after migration 0017.
    op.execute("DROP POLICY mood_record_privacy_worker ON health.mood_record")
    op.execute("""
        CREATE POLICY mood_record_privacy_worker_select ON health.mood_record
        FOR SELECT TO gutcare_privacy_worker
        USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY mood_record_privacy_worker_delete ON health.mood_record
        FOR DELETE TO gutcare_privacy_worker
        USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    """)
    op.execute("REVOKE UPDATE ON health.mood_record FROM gutcare_privacy_worker")
    op.execute("GRANT SELECT, DELETE ON health.mood_record TO gutcare_privacy_worker")

    # Existing soft-deleted rows get their original seven-day deadline.
    # The migration role is subject to FORCE RLS, so make this deterministic
    # backfill visible only inside the transactional migration and restore RLS
    # before it commits.
    op.execute("ALTER TABLE health.mood_record DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy.mood_purge_queue DISABLE ROW LEVEL SECURITY")
    op.execute("""
        INSERT INTO privacy.mood_purge_queue (patient_id, mood_record_id, purge_after)
        SELECT patient_id, id, deleted_at + interval '7 days'
        FROM health.mood_record WHERE deleted_at IS NOT NULL
        ON CONFLICT (patient_id, mood_record_id) DO NOTHING
    """)
    op.execute("ALTER TABLE health.mood_record ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE health.mood_record FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy.mood_purge_queue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy.mood_purge_queue FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("ALTER TABLE privacy.export_operation DISABLE ROW LEVEL SECURITY")
    has_mood_exports = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM privacy.export_operation "
            "WHERE categories @> ARRAY['mood']::varchar[])"
        )
    )
    op.execute("ALTER TABLE privacy.export_operation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy.export_operation FORCE ROW LEVEL SECURITY")
    if has_mood_exports:
        raise RuntimeError(
            "Cannot downgrade 0026_h3b_mood_privacy_lifecycle while mood export operations exist; "
            "preserve the export history and use an explicitly approved migration before downgrade."
        )
    op.execute("DROP POLICY mood_record_privacy_worker_select ON health.mood_record")
    op.execute("DROP POLICY mood_record_privacy_worker_delete ON health.mood_record")
    op.execute("""
        CREATE POLICY mood_record_privacy_worker ON health.mood_record
        FOR ALL TO gutcare_privacy_worker USING (true) WITH CHECK (true)
    """)
    op.execute("GRANT UPDATE ON health.mood_record TO gutcare_privacy_worker")
    op.drop_table("mood_purge_queue", schema="privacy")
    op.drop_constraint("ck_export_operation_categories", "export_operation", schema="privacy")
    op.create_check_constraint(
        "ck_export_operation_categories",
        "export_operation",
        "categories <@ ARRAY['profile','consents','medical_documents','files','diet','stool',"
        "'symptoms','medication','activity','analysis','advice','alerts','notifications']::varchar[]",
        schema="privacy",
    )
