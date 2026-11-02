"""Consume one-time boundary grants durably."""

from alembic import op
import sqlalchemy as sa

revision = "0006_action_grants"
down_revision = "0005_teammates_computers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("grant_consumed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("approval_requests", "grant_consumed_at")
