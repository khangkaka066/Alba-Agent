"""Use timezone-aware timestamps for runtime and approval records.

Revision ID: 0004_timestamps
Revises: 0003_approval_gate
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_timestamps"
down_revision = "0003_approval_gate"
branch_labels = None
depends_on = None

TIMESTAMP_COLUMNS = {
    "tenants": ("created_at",),
    "workspaces": ("created_at",),
    "service_api_keys": ("revoked_at",),
    "workflow_runs": ("started_at", "finished_at"),
    "approval_requests": ("decided_at",),
}


def upgrade() -> None:
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column,
                type_=sa.DateTime(timezone=True),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column,
                type_=sa.DateTime(timezone=False),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
