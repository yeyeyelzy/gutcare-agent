"""Expose aggregate-only operational backlog metrics to the API role."""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_operations_metrics_snapshot"
down_revision: str | None = "0019_nfr_file_deletion_job_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_METRICS_POLICIES = (
    ("health", "notification_outbox"),
    ("integration", "file_deletion_job"),
    ("integration", "file_orphan_cleanup_job"),
    ("privacy", "object_inventory"),
    ("privacy", "export_operation"),
)


def upgrade() -> None:
    for schema, table in _METRICS_POLICIES:
        op.execute(
            f"CREATE POLICY metrics_migrator_read ON {schema}.{table} "
            "FOR SELECT TO gutcare_migrator USING (true)"
        )

    op.execute(
        """
        CREATE FUNCTION public.gutcare_metrics_snapshot()
        RETURNS TABLE(queue text, state text, item_count bigint, oldest_age_seconds bigint)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, health, integration, privacy
        AS $metrics$
            SELECT 'notification_outbox', 'backlog', count(*)::bigint,
                   COALESCE(EXTRACT(EPOCH FROM now() - min(created_at))::bigint, 0)
              FROM health.notification_outbox WHERE status IN ('pending','processing')
            UNION ALL
            SELECT 'notification_outbox', 'dead_letter', count(*)::bigint, 0::bigint
              FROM health.notification_outbox WHERE status = 'dead_letter'
            UNION ALL
            SELECT 'file_deletion', 'backlog', count(*)::bigint,
                   COALESCE(EXTRACT(EPOCH FROM now() - min(due_at))::bigint, 0)
              FROM integration.file_deletion_job WHERE status IN ('pending','processing')
            UNION ALL
            SELECT 'file_orphan_cleanup', 'backlog', count(*)::bigint,
                   COALESCE(EXTRACT(EPOCH FROM now() - min(due_at))::bigint, 0)
              FROM integration.file_orphan_cleanup_job WHERE status IN ('pending','processing')
            UNION ALL
            SELECT 'privacy_deletion', 'backlog', count(*)::bigint,
                   COALESCE(EXTRACT(EPOCH FROM now() - min(due_at))::bigint, 0)
              FROM privacy.deletion_operation
             WHERE status IN ('pending','overdue','processing')
               AND (status = 'overdue' OR due_at < now())
            UNION ALL
            SELECT 'privacy_deletion', 'dead_letter', count(*)::bigint, 0::bigint
              FROM privacy.deletion_operation WHERE status = 'dead_letter'
            UNION ALL
            SELECT 'privacy_inventory', 'backlog', count(*)::bigint,
                   COALESCE(
                       EXTRACT(EPOCH FROM now() - min(operation.requested_at))::bigint, 0
                   )
              FROM privacy.object_inventory inventory
              JOIN privacy.deletion_operation operation ON operation.id = inventory.operation_id
             WHERE inventory.status IN ('pending','deleting','failed')
            UNION ALL
            SELECT 'export_cleanup', 'backlog', count(*)::bigint,
                   COALESCE(EXTRACT(EPOCH FROM now() - min(expires_at))::bigint, 0)
              FROM privacy.export_operation
             WHERE object_key IS NOT NULL
               AND (status IN ('cancelled','expired','failed') OR expires_at < now())
        $metrics$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.gutcare_metrics_snapshot() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.gutcare_metrics_snapshot() TO gutcare_app")


def downgrade() -> None:
    op.execute("REVOKE EXECUTE ON FUNCTION public.gutcare_metrics_snapshot() FROM gutcare_app")
    op.execute("DROP FUNCTION public.gutcare_metrics_snapshot()")
    for schema, table in reversed(_METRICS_POLICIES):
        op.execute(f"DROP POLICY metrics_migrator_read ON {schema}.{table}")
