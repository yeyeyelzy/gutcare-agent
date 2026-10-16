"""Make family_id point to a retained root session used for family locking."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_refresh_family_root_fk"
down_revision: str | None = "0002_refresh_family"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Earlier 0002 rows used an opaque family UUID. Normalize each lineage to its
    # oldest root session before adding the self-reference used by SELECT FOR UPDATE.
    op.execute(
        """
        WITH roots AS (
            SELECT family_id AS previous_family_id,
                   (array_agg(id ORDER BY created_at, id))[1] AS root_id
            FROM iam.refresh_session
            WHERE parent_session_id IS NULL
            GROUP BY family_id
        )
        UPDATE iam.refresh_session AS session
        SET family_id = roots.root_id
        FROM roots
        WHERE session.family_id = roots.previous_family_id
        """
    )
    op.create_foreign_key(
        "fk_refresh_session_family_root",
        "refresh_session",
        "refresh_session",
        ["family_id"],
        ["id"],
        source_schema="iam",
        referent_schema="iam",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    # Keep normalized root IDs; removing the FK restores the 0002-compatible shape.
    op.drop_constraint("fk_refresh_session_family_root", "refresh_session", schema="iam")
