"""Record whether each model call was metered or covered by a flat subscription plan.

Revision ID: 0015_billing_mode
Revises: 0014_team_evolution
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_billing_mode"
down_revision = "0014_team_evolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("token_usage_logs", sa.Column("billing_mode", sa.String(24), nullable=False, server_default="METERED"))
    op.create_check_constraint("ck_usage_billing_mode", "token_usage_logs", "billing_mode IN ('METERED','SUBSCRIPTION_INCLUDED')")


def downgrade() -> None:
    op.drop_constraint("ck_usage_billing_mode", "token_usage_logs", type_="check")
    op.drop_column("token_usage_logs", "billing_mode")
