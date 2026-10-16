"""Add F12 in-app notifications and strict transactional outbox."""

# Migration SQL keeps PostgreSQL CHECKs and trigger bodies readable as single statements.
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_f12_notifications"
down_revision: str | None = "0014_f09_advice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _secure(table: str) -> None:
    op.execute(f"ALTER TABLE health.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE health.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_patient_isolation ON health.{table} "
        "USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid) "
        "WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA health TO gutcare_app, gutcare_notification_worker")
    op.create_table(
        "notification_preference",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ordinary_in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("quiet_start", sa.Time()),
        sa.Column("quiet_end", sa.Time()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(quiet_start IS NULL) = (quiet_end IS NULL)", name="ck_notification_quiet_pair"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="health",
    )
    op.create_table(
        "notification_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("deduplication_key", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "event_type IN ('analysis_completed','advice_created','risk_alert_created','checkin_reminder')",
            name="ck_notification_outbox_event",
        ),
        sa.CheckConstraint(
            "target_type IN ('analysis_task','advice','risk_alert','medication_checkin')",
            name="ck_notification_outbox_target",
        ),
        sa.CheckConstraint(
            "priority IN ('ordinary','risk')", name="ck_notification_outbox_priority"
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','dispatched','suppressed','dead_letter')",
            name="ck_notification_outbox_status",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 8", name="ck_notification_outbox_attempts"),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ?& ARRAY['event_type','patient_id','target_type','target_id','occurred_at','priority','deduplication_key'] AND (payload - ARRAY['event_type','patient_id','target_type','target_id','occurred_at','priority','deduplication_key']) = '{}'::jsonb",
            name="ck_notification_outbox_payload_allowlist",
        ),
        sa.CheckConstraint(
            "payload->>'event_type'=event_type AND payload->>'patient_id'=patient_id::text AND payload->>'target_type'=target_type AND payload->>'target_id'=target_id::text AND (payload->>'occurred_at')::timestamptz=occurred_at AND payload->>'priority'=priority AND payload->>'deduplication_key'=deduplication_key",
            name="ck_notification_outbox_payload_matches",
        ),
        sa.CheckConstraint(
            "(event_type='risk_alert_created' AND target_type='risk_alert' AND priority='risk') OR (event_type='analysis_completed' AND target_type='analysis_task' AND priority='ordinary') OR (event_type='advice_created' AND target_type='advice' AND priority='ordinary') OR (event_type='checkin_reminder' AND target_type='medication_checkin' AND priority='ordinary')",
            name="ck_notification_outbox_event_target",
        ),
        sa.UniqueConstraint("patient_id", "deduplication_key", name="uq_notification_outbox_dedup"),
        sa.UniqueConstraint("id", "patient_id", name="uq_notification_outbox_id_patient"),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="health",
    )
    op.create_table(
        "patient_notification",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("target_type", sa.String(40)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "target_unavailable", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("deduplication_key", sa.String(160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "category IN ('analysis','advice','risk','medication_reminder')",
            name="ck_patient_notification_category",
        ),
        sa.CheckConstraint(
            "priority IN ('ordinary','risk')", name="ck_patient_notification_priority"
        ),
        sa.CheckConstraint(
            "(target_unavailable = true AND target_type IS NULL AND target_id IS NULL) OR (target_unavailable = false AND target_type IS NOT NULL AND target_id IS NOT NULL)",
            name="ck_notification_target_shape",
        ),
        sa.UniqueConstraint(
            "patient_id", "deduplication_key", name="uq_patient_notification_dedup"
        ),
        sa.UniqueConstraint("id", "patient_id", name="uq_patient_notification_id_patient"),
        sa.ForeignKeyConstraint(
            ["outbox_id", "patient_id"],
            ["health.notification_outbox.id", "health.notification_outbox.patient_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["health.patient_profile.id"], ondelete="CASCADE"),
        schema="health",
    )
    op.create_index(
        "ix_patient_notification_cursor",
        "patient_notification",
        ["patient_id", "created_at", "id"],
        schema="health",
    )
    for name in ("notification_preference", "notification_outbox", "patient_notification"):
        _secure(name)

    op.execute(
        "CREATE POLICY notification_outbox_source_insert ON health.notification_outbox FOR INSERT TO gutcare_app, gutcare_worker, gutcare_analysis_worker WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )

    # Domain triggers build only the frozen allowlist payload, within the source transaction.
    op.execute("""CREATE FUNCTION health.enqueue_notification() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,health,analysis,safety AS $$
DECLARE et text; tt text; tid uuid; pid uuid; pr text; occurred timestamptz; dk text;
BEGIN
 IF TG_TABLE_SCHEMA='analysis' AND TG_TABLE_NAME='analysis_task' THEN
   IF NEW.status NOT IN ('succeeded','partial','failed') OR (TG_OP='UPDATE' AND OLD.status=NEW.status) THEN RETURN NEW; END IF;
   et := 'analysis_completed'; tt := 'analysis_task'; tid := NEW.id; pid := NEW.patient_id; pr := 'ordinary'; occurred := NEW.updated_at; dk := 'analysis:'||NEW.id||':'||NEW.status;
 ELSIF TG_TABLE_NAME='health_advice' THEN
   et := 'advice_created'; tt := 'advice'; tid := NEW.id; pid := NEW.patient_id; pr := 'ordinary'; occurred := NEW.created_at; dk := 'advice:'||NEW.id;
 ELSIF TG_TABLE_NAME='risk_alert' THEN
   et := 'risk_alert_created'; tt := 'risk_alert'; tid := NEW.id; pid := NEW.patient_id; pr := 'risk'; occurred := NEW.triggered_at; dk := 'risk:'||NEW.id;
 ELSIF TG_TABLE_NAME='medication_checkin' THEN
   IF NEW.status <> 'pending' THEN RETURN NEW; END IF;
   et := 'checkin_reminder'; tt := 'medication_checkin'; tid := NEW.id; pid := NEW.patient_id; pr := 'ordinary'; occurred := NEW.created_at; dk := 'checkin:'||NEW.schedule_id||':'||NEW.local_date;
 ELSE RETURN NEW; END IF;
 INSERT INTO health.notification_outbox(patient_id,event_type,target_type,target_id,occurred_at,priority,deduplication_key,payload)
 VALUES(pid,et,tt,tid,occurred,pr,dk,jsonb_build_object('event_type',et,'patient_id',pid,'target_type',tt,'target_id',tid,'occurred_at',occurred,'priority',pr,'deduplication_key',dk)) ON CONFLICT(patient_id,deduplication_key) DO NOTHING;
 RETURN NEW;
END $$""")
    op.execute(
        "CREATE TRIGGER trg_analysis_notification AFTER INSERT OR UPDATE OF status ON analysis.analysis_task FOR EACH ROW EXECUTE FUNCTION health.enqueue_notification()"
    )
    op.execute(
        "CREATE TRIGGER trg_advice_notification AFTER INSERT ON analysis.health_advice FOR EACH ROW EXECUTE FUNCTION health.enqueue_notification()"
    )
    op.execute(
        "CREATE TRIGGER trg_risk_notification AFTER INSERT ON safety.risk_alert FOR EACH ROW EXECUTE FUNCTION health.enqueue_notification()"
    )
    op.execute(
        "CREATE TRIGGER trg_checkin_notification AFTER INSERT ON health.medication_checkin FOR EACH ROW EXECUTE FUNCTION health.enqueue_notification()"
    )
    op.execute(
        "CREATE POLICY notification_worker_select ON health.notification_outbox FOR SELECT TO gutcare_notification_worker USING (true)"
    )
    op.execute(
        "CREATE POLICY notification_worker_update ON health.notification_outbox FOR UPDATE TO gutcare_notification_worker USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY notification_worker_patient_notifications ON health.patient_notification FOR INSERT TO gutcare_notification_worker WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY notification_worker_preferences ON health.notification_preference FOR SELECT TO gutcare_notification_worker USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)"
    )
    op.execute(
        "REVOKE ALL ON health.notification_preference, health.notification_outbox, health.patient_notification FROM PUBLIC, gutcare_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON health.notification_preference, health.patient_notification TO gutcare_app"
    )
    op.execute("GRANT SELECT, UPDATE ON health.notification_outbox TO gutcare_notification_worker")
    op.execute(
        "GRANT INSERT ON health.notification_outbox TO gutcare_app, gutcare_worker, gutcare_analysis_worker"
    )
    op.execute("GRANT SELECT ON health.notification_preference TO gutcare_notification_worker")
    op.execute("GRANT INSERT ON health.patient_notification TO gutcare_notification_worker")


def downgrade() -> None:
    for trigger, table in (
        ("trg_checkin_notification", "health.medication_checkin"),
        ("trg_risk_notification", "safety.risk_alert"),
        ("trg_advice_notification", "analysis.health_advice"),
        ("trg_analysis_notification", "analysis.analysis_task"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS health.enqueue_notification()")
    for table in ("patient_notification", "notification_outbox", "notification_preference"):
        op.drop_table(table, schema="health")
