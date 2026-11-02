"""Persist approval gate identity and required role.

Revision ID: 0003_approval_gate
Revises: 0002_budget_overage
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_approval_gate"
down_revision = "0002_budget_overage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("node_id", sa.String(100), nullable=True))
    op.add_column("approval_requests", sa.Column("required_role", sa.String(16), nullable=True))
    op.add_column("approval_requests", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE approval_requests SET node_id = 'legacy', required_role = 'admin'")
    op.alter_column("approval_requests", "node_id", nullable=False)
    op.alter_column("approval_requests", "required_role", nullable=False)
    op.create_check_constraint("ck_approval_required_role", "approval_requests", "required_role IN ('owner','admin','builder')")


def downgrade() -> None:
    op.drop_constraint("ck_approval_required_role", "approval_requests", type_="check")
    op.drop_column("approval_requests", "expires_at")
    op.drop_column("approval_requests", "required_role")
    op.drop_column("approval_requests", "node_id")
