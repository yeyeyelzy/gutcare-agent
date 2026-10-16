"""Track refresh-token families and rotation lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_refresh_family"
down_revision: str | None = "0001_f01_email_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_session",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="iam",
    )
    op.execute(sa.text("UPDATE iam.refresh_session SET family_id = id WHERE family_id IS NULL"))
    op.alter_column("refresh_session", "family_id", nullable=False, schema="iam")
    op.add_column(
        "refresh_session",
        sa.Column("parent_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="iam",
    )
    op.add_column(
        "refresh_session",
        sa.Column("replaced_by_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="iam",
    )
    op.create_foreign_key(
        "fk_refresh_session_parent",
        "refresh_session",
        "refresh_session",
        ["parent_session_id"],
        ["id"],
        source_schema="iam",
        referent_schema="iam",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_refresh_session_successor",
        "refresh_session",
        "refresh_session",
        ["replaced_by_session_id"],
        ["id"],
        source_schema="iam",
        referent_schema="iam",
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_refresh_session_successor", "refresh_session", ["replaced_by_session_id"], schema="iam"
    )
    op.create_index(
        "ix_refresh_session_family", "refresh_session", ["family_id", "revoked_at"], schema="iam"
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_session_family", table_name="refresh_session", schema="iam")
    op.drop_constraint("uq_refresh_session_successor", "refresh_session", schema="iam")
    op.drop_constraint("fk_refresh_session_successor", "refresh_session", schema="iam")
    op.drop_constraint("fk_refresh_session_parent", "refresh_session", schema="iam")
    op.drop_column("refresh_session", "replaced_by_session_id", schema="iam")
    op.drop_column("refresh_session", "parent_session_id", schema="iam")
    op.drop_column("refresh_session", "family_id", schema="iam")
