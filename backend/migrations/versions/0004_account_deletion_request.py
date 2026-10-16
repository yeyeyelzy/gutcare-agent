"""Track account deletion requests and immediate deactivation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_account_deletion_request"
down_revision: str | None = "0003_refresh_family_root_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_request",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_account_deletion_request_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["iam.user_account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_account_deletion_request_user_id"),
        schema="iam",
    )
    op.execute("ALTER TABLE iam.account_deletion_request ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE iam.account_deletion_request FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY account_deletion_request_owner ON iam.account_deletion_request "
        "USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid) "
        "WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.drop_table("account_deletion_request", schema="iam")
