"""Provider catalog metadata and workspace-scoped credential settings.

Revision ID: 0008_provider_settings
Revises: 0007_workflow_inputs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_provider_settings"
down_revision = "0007_workflow_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_credentials", sa.Column("preset_id", sa.String(80), nullable=False, server_default=""))
    op.add_column("model_credentials", sa.Column("base_url", sa.String(1000), nullable=True))
    op.add_column("model_credentials", sa.Column("status", sa.String(16), nullable=False, server_default="untested"))
    op.add_column("model_credentials", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("model_credentials", sa.Column("available_models", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("model_credentials", sa.Column("default_models", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("model_credentials", sa.Column("settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("model_credentials", sa.Column("live_balance", JSONB(), nullable=True))
    op.add_column("model_credentials", sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("model_credentials", sa.Column("safe_error", sa.String(500), nullable=True))
    op.create_index("ix_model_credentials_active_provider", "model_credentials", ["tenant_id", "workspace_id", "provider", "status"])


def downgrade() -> None:
    op.drop_index("ix_model_credentials_active_provider", table_name="model_credentials")
    for name in ("safe_error", "last_tested_at", "live_balance", "settings", "default_models", "available_models", "is_default", "status", "base_url", "preset_id"):
        op.drop_column("model_credentials", name)
