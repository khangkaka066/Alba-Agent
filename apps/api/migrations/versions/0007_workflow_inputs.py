"""Durably retain queued workflow inputs before worker dispatch.

Revision ID: 0007_workflow_inputs
Revises: 0006_action_grants
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_workflow_inputs"
down_revision = "0006_action_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("input_data", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "input_data")
