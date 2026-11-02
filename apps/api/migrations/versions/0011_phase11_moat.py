"""Self-healing proposals, golden traces and model recommendations.

Revision ID: 0011_phase11_moat
Revises: 0010_learning_transfer
"""

from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011_phase11_moat"
down_revision = "0010_learning_transfer"
branch_labels = None
depends_on = None


def _scoped_table(name: str, *columns: Any, constraints: tuple[Any, ...] = ()) -> None:
    op.create_table(
        name,
        *columns,
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id"], ["workspaces.tenant_id", "workspaces.id"], ondelete="CASCADE", name=f"fk_{name}_workspace_scope"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "id", name=f"uq_{name}_scope_id"),
        *constraints,
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])
    tenant = "NULLIF(current_setting('nexus.tenant_id', true), '')::uuid"
    workspace = "NULLIF(current_setting('nexus.workspace_id', true), '')::uuid"
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {name}_scope ON {name} USING (tenant_id = {tenant} AND workspace_id = {workspace}) WITH CHECK (tenant_id = {tenant} AND workspace_id = {workspace})")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO nexus_app")


def upgrade() -> None:
    _scoped_table(
        "prompt_patch_proposals",
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_approval_id", UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("target_field", sa.String(32), nullable=False),
        sa.Column("original_output", sa.Text(), nullable=False),
        sa.Column("corrected_output", sa.Text(), nullable=False),
        sa.Column("reviewer_comment", sa.Text(), nullable=False),
        sa.Column("unified_diff", sa.Text(), nullable=False),
        sa.Column("replacement_value", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("applied_workflow_version", sa.Integer(), nullable=True),
        constraints=(
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "workflow_id"], ["workflows.tenant_id", "workflows.workspace_id", "workflows.id"], name="fk_prompt_patch_proposals_workflow_id_scope", ondelete="CASCADE"),
            sa.CheckConstraint("status IN ('pending','applied','dismissed')", name="ck_prompt_patch_status"),
        ),
    )
    _scoped_table(
        "golden_traces",
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("task_signature", sa.String(128), nullable=False),
        sa.Column("input_payload", JSONB, nullable=False),
        sa.Column("verified_output", JSONB, nullable=False),
        sa.Column("model_used", sa.String(200), nullable=False),
        sa.Column("cost_usd", sa.Numeric(14, 8), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        constraints=(
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "run_id"], ["workflow_runs.tenant_id", "workflow_runs.workspace_id", "workflow_runs.id"], name="fk_golden_traces_run_id_scope", ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "workspace_id", "run_id", "agent_id", "task_signature", name="uq_golden_trace_run_agent_task"),
        ),
    )
    op.create_index("ix_golden_trace_task", "golden_traces", ["tenant_id", "workspace_id", "agent_id", "task_signature"])
    _scoped_table(
        "distillation_recommendations",
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("task_signature", sa.String(128), nullable=False),
        sa.Column("candidate_model", sa.String(200), nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("few_shot_examples", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="recommended"),
        constraints=(sa.CheckConstraint("status IN ('recommended','applied','rolled_back','rejected')", name="ck_distillation_recommendation_status"),),
    )


def downgrade() -> None:
    for name in ("distillation_recommendations", "golden_traces", "prompt_patch_proposals"):
        op.execute(f"DROP POLICY IF EXISTS {name}_scope ON {name}")
        op.drop_table(name)
