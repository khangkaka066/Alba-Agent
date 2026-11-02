"""Team topology generations, fitness history and per-lineage evolution policy.

Revision ID: 0014_team_evolution
Revises: 0013_auth_email_lookup
"""
from typing import Any
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0014_team_evolution"
down_revision = "0013_auth_email_lookup"
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
    t = "NULLIF(current_setting('nexus.tenant_id', true), '')::uuid"
    w = "NULLIF(current_setting('nexus.workspace_id', true), '')::uuid"
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {name}_scope ON {name} USING (tenant_id = {t} AND workspace_id = {w}) WITH CHECK (tenant_id = {t} AND workspace_id = {w})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO nexus_app")


def upgrade() -> None:
    _scoped(
        "workflow_topology_versions",
        sa.Column("lineage_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("spec", JSONB(), nullable=False),
        sa.Column("mutation_ops_applied", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evolution_rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("diagnoses", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("diff", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("product_quality_score", sa.Float(), nullable=True),
        sa.Column("artifact_completeness_rate", sa.Float(), nullable=True),
        sa.Column("avg_human_rating", sa.Float(), nullable=True),
        sa.Column("avg_cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("avg_latency_seconds", sa.Float(), nullable=True),
        sa.Column("efficiency", sa.Float(), nullable=True),
        sa.Column("fitness", sa.Float(), nullable=True),
        sa.Column("runs_observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        constraints=(
            sa.UniqueConstraint("tenant_id", "workspace_id", "lineage_id", "version_number", name="uq_topology_lineage_version"),
            sa.CheckConstraint("status IN ('proposed','active','superseded','rolled_back','rejected')", name="ck_topology_status"),
            sa.CheckConstraint("origin IN ('manual','post_run','mid_run','autonomous','baseline')", name="ck_topology_origin"),
        ),
    )
    op.create_index("ix_topology_lineage", "workflow_topology_versions", ["tenant_id", "workspace_id", "lineage_id"])
    op.create_index("ix_topology_workflow", "workflow_topology_versions", ["tenant_id", "workspace_id", "workflow_id"])
    _scoped(
        "workflow_evolution_policies",
        sa.Column("lineage_id", UUID(as_uuid=True), nullable=False),
        sa.Column("auto_evolve_policy", sa.String(20), nullable=False, server_default="SUGGEST_FIRST"),
        sa.Column("active_workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=False),
        constraints=(
            sa.UniqueConstraint("tenant_id", "workspace_id", "lineage_id", name="uq_evolution_policy_lineage"),
            sa.CheckConstraint("auto_evolve_policy IN ('SUGGEST_FIRST','FULLY_AUTONOMOUS')", name="ck_evolution_policy"),
        ),
    )


def downgrade() -> None:
    for name in ("workflow_evolution_policies", "workflow_topology_versions"):
        op.execute(f"DROP POLICY IF EXISTS {name}_scope ON {name}")
        op.drop_table(name)
