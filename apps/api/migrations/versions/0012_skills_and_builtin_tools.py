"""Workspace scoped skill registry and built-in tool switches.

Revision ID: 0012_skills_and_builtin_tools
Revises: 0011_phase11_moat
"""
from typing import Any
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012_skills_and_builtin_tools"
down_revision = "0011_phase11_moat"
branch_labels = None
depends_on = None


def _scoped(name: str, *columns: Any, constraints: tuple[Any, ...] = ()) -> None:
    op.create_table(name, *columns,
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id"], ["workspaces.tenant_id", "workspaces.id"], ondelete="CASCADE", name=f"fk_{name}_workspace_scope"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "id", name=f"uq_{name}_scope_id"), *constraints)
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])
    t="NULLIF(current_setting('nexus.tenant_id', true), '')::uuid"; w="NULLIF(current_setting('nexus.workspace_id', true), '')::uuid"
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {name}_scope ON {name} USING (tenant_id = {t} AND workspace_id = {w}) WITH CHECK (tenant_id = {t} AND workspace_id = {w})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO nexus_app")


def upgrade() -> None:
    _scoped("agent_skills", sa.Column("slug", sa.String(120), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("category", sa.String(80), nullable=False), sa.Column("description", sa.String(1000), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()), constraints=(sa.UniqueConstraint("tenant_id", "workspace_id", "slug", name="uq_agent_skill_scope_slug"),))
    _scoped("workspace_builtin_tools", sa.Column("tool_id", sa.String(80), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), constraints=(sa.UniqueConstraint("tenant_id", "workspace_id", "tool_id", name="uq_workspace_builtin_tool"),))


def downgrade() -> None:
    for name in ("workspace_builtin_tools", "agent_skills"):
        op.execute(f"DROP POLICY IF EXISTS {name}_scope ON {name}")
        op.drop_table(name)
