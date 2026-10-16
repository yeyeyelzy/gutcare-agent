"""Persist the immutable mood count and consent-scoped snapshot summary."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_f14_analysis_mood"
down_revision: str | None = "0024_f14_mood_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_task",
        sa.Column(
            "input_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("jsonb_build_object('included_mood_record_count', 0)"),
        ),
        schema="analysis",
    )
    # Migration owner must see all patients for this deterministic backfill;
    # restore FORCE RLS in the same transaction before migration completion.
    op.execute("ALTER TABLE analysis.analysis_task NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        UPDATE analysis.analysis_task t
        SET input_summary=jsonb_build_object(
            'included_mood_record_count', COALESCE((
                SELECT count(*) FROM analysis.task_input_snapshot s,
                     jsonb_array_elements(s.snapshot_payload->'records') r
                WHERE s.task_id=t.id AND s.patient_id=t.patient_id
                  AND r->>'record_type'='mood_record'
            ), 0)
        )
    """)
    op.create_check_constraint(
        "ck_analysis_task_input_summary_mood_count",
        "analysis_task",
        "jsonb_typeof(input_summary) = 'object' AND "
        "jsonb_typeof(input_summary->'included_mood_record_count') = 'number' AND "
        "(input_summary->>'included_mood_record_count')::numeric >= 0 AND "
        "mod((input_summary->>'included_mood_record_count')::numeric, 1) = 0",
        schema="analysis",
    )
    op.execute("""
        CREATE FUNCTION analysis.reject_input_summary_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.input_summary IS DISTINCT FROM OLD.input_summary THEN
            RAISE EXCEPTION 'analysis input_summary is immutable';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER analysis_task_input_summary_immutable
        BEFORE UPDATE OF input_summary ON analysis.analysis_task
        FOR EACH ROW EXECUTE FUNCTION analysis.reject_input_summary_mutation()
    """)
    op.execute("ALTER TABLE analysis.analysis_task_idempotency NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        UPDATE analysis.analysis_task_idempotency i
        SET response_snapshot=jsonb_set(
            i.response_snapshot, '{input_summary}', t.input_summary, true
        )
        FROM analysis.analysis_task t
        WHERE i.task_id=t.id AND i.patient_id=t.patient_id
    """)
    op.execute("ALTER TABLE analysis.analysis_task_idempotency FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE analysis.analysis_task FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE analysis.analysis_task_idempotency NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        UPDATE analysis.analysis_task_idempotency
        SET response_snapshot=response_snapshot - 'input_summary'
        WHERE response_snapshot ? 'input_summary'
    """)
    op.execute("ALTER TABLE analysis.analysis_task_idempotency FORCE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER analysis_task_input_summary_immutable ON analysis.analysis_task")
    op.execute("DROP FUNCTION analysis.reject_input_summary_mutation()")
    op.drop_constraint(
        "ck_analysis_task_input_summary_mood_count", "analysis_task", schema="analysis"
    )
    op.drop_column("analysis_task", "input_summary", schema="analysis")
