"""Add a narrow readiness signal for privacy deletion replay."""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_readiness_gate"
down_revision: str | None = "0017_f13_privacy_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON TABLE public.alembic_version TO gutcare_app")
    for table in ("deletion_operation", "deletion_step", "object_inventory"):
        op.execute(
            f"CREATE POLICY readiness_migrator_read ON privacy.{table} "
            "FOR SELECT TO gutcare_migrator USING (true)"
        )
    op.execute("""
        CREATE FUNCTION privacy.replay_ready() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, privacy
        AS $function$
            SELECT NOT EXISTS (
                SELECT 1 FROM privacy.deletion_operation
                WHERE status <> 'completed'
            )
            AND NOT EXISTS (
                SELECT 1 FROM privacy.deletion_step
                WHERE status <> 'completed'
            )
            AND NOT EXISTS (
                SELECT 1 FROM privacy.object_inventory
                WHERE status <> 'deleted'
            )
        $function$
    """)
    op.execute("ALTER FUNCTION privacy.replay_ready() OWNER TO gutcare_migrator")
    op.execute("REVOKE ALL ON FUNCTION privacy.replay_ready() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION privacy.replay_ready() TO gutcare_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON TABLE public.alembic_version FROM gutcare_app")
    op.execute("REVOKE EXECUTE ON FUNCTION privacy.replay_ready() FROM gutcare_app")
    op.execute("DROP FUNCTION privacy.replay_ready()")
    for table in ("deletion_operation", "deletion_step", "object_inventory"):
        op.execute(f"DROP POLICY readiness_migrator_read ON privacy.{table}")
