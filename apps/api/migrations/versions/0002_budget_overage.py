"""Record provider overage without dropping usage logs.

Revision ID: 0002_budget_overage
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_budget_overage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_budgets", sa.Column("overage_usd", sa.Numeric(18, 8), nullable=False, server_default="0"))
    op.drop_constraint("ck_tenant_budget_nonnegative", "tenant_budgets", type_="check")
    op.create_check_constraint("ck_tenant_budget_nonnegative", "tenant_budgets", "remaining_usd >= 0 AND reserved_usd >= 0 AND overage_usd >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_tenant_budget_nonnegative", "tenant_budgets", type_="check")
    op.create_check_constraint("ck_tenant_budget_nonnegative", "tenant_budgets", "remaining_usd >= 0 AND reserved_usd >= 0")
    op.drop_column("tenant_budgets", "overage_usd")
