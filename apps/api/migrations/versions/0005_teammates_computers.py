"""Persistent computers, bot history, routine checkpoints, and routine approvals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from typing import Any

revision = "0005_teammates_computers"
down_revision = "0004_timestamps"
branch_labels = None
depends_on = None

TABLES = ("bot_messages", "routine_runs", "sandbox_computers")
SCOPE = "tenant_id = NULLIF(current_setting('nexus.tenant_id', true), '')::uuid AND workspace_id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid"


def _scope(table: str) -> None:
    op.create_unique_constraint(f"uq_{table}_scope_id", table, ["tenant_id", "workspace_id", "id"])
    op.create_foreign_key(f"fk_{table}_workspace_scope", table, "workspaces", ["tenant_id", "workspace_id"], ["tenant_id", "id"], ondelete="CASCADE")
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_scope ON {table} USING ({SCOPE}) WITH CHECK ({SCOPE})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def _base_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("bot_routines", sa.Column("workflow_id", sa.UUID(), nullable=True))
    op.add_column("bot_routines", sa.Column("interval_seconds", sa.Integer(), nullable=True))
    op.add_column("bot_routines", sa.Column("allowed_actions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_foreign_key("fk_bot_routines_workflow_id_scope", "bot_routines", "workflows", ["tenant_id", "workspace_id", "workflow_id"], ["tenant_id", "workspace_id", "id"], ondelete="CASCADE")
    op.create_check_constraint("ck_routine_interval_positive", "bot_routines", "interval_seconds IS NULL OR interval_seconds > 0")

    op.create_table(
        "bot_messages",
        *_base_columns(),
        sa.Column("bot_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_bot_message_role"),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "bot_id"], ["persistent_bots.tenant_id", "persistent_bots.workspace_id", "persistent_bots.id"], name="fk_bot_messages_bot_id_scope", ondelete="CASCADE"),
    )
    _scope("bot_messages")
    op.create_index("ix_bot_messages_thread", "bot_messages", ["tenant_id", "workspace_id", "bot_id", "thread_id", "created_at"])

    op.create_table(
        "routine_runs",
        *_base_columns(),
        sa.Column("bot_id", sa.UUID(), nullable=False),
        sa.Column("routine_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column("workflow_run_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("status IN ('queued','running','paused','completed','failed')", name="ck_routine_run_status"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "routine_id", "scheduled_for", name="uq_routine_scheduled"),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "routine_id"], ["bot_routines.tenant_id", "bot_routines.workspace_id", "bot_routines.id"], name="fk_routine_runs_routine_id_scope", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "bot_id"], ["persistent_bots.tenant_id", "persistent_bots.workspace_id", "persistent_bots.id"], name="fk_routine_runs_bot_id_scope", ondelete="CASCADE"),
    )
    _scope("routine_runs")

    op.create_table(
        "sandbox_computers",
        *_base_columns(),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("bot_id", sa.UUID(), nullable=True),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.CheckConstraint("visibility IN ('shared','private')", name="ck_computer_visibility"),
        sa.CheckConstraint("status IN ('provisioning','running','failed','terminated')", name="ck_computer_status"),
        sa.CheckConstraint("visibility = 'shared' OR bot_id IS NOT NULL OR run_id IS NOT NULL", name="ck_private_computer_owner"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "run_id", name="uq_computer_run"),
    )
    _scope("sandbox_computers")

    op.alter_column("approval_requests", "run_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("approval_requests", sa.Column("routine_run_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_approval_requests_routine_run_id_scope", "approval_requests", "routine_runs", ["tenant_id", "workspace_id", "routine_run_id"], ["tenant_id", "workspace_id", "id"], ondelete="CASCADE")
    op.create_check_constraint("ck_approval_one_run", "approval_requests", "(run_id IS NULL) <> (routine_run_id IS NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_approval_one_run", "approval_requests", type_="check")
    op.drop_constraint("fk_approval_requests_routine_run_id_scope", "approval_requests", type_="foreignkey")
    op.drop_column("approval_requests", "routine_run_id")
    op.alter_column("approval_requests", "run_id", existing_type=sa.UUID(), nullable=False)
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY {table}_scope ON {table}")
        op.drop_table(table)
    op.drop_constraint("ck_routine_interval_positive", "bot_routines", type_="check")
    op.drop_constraint("fk_bot_routines_workflow_id_scope", "bot_routines", type_="foreignkey")
    op.drop_column("bot_routines", "interval_seconds")
    op.drop_column("bot_routines", "allowed_actions")
    op.drop_column("bot_routines", "workflow_id")
