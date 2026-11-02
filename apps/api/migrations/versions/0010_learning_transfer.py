"""Tenant-scoped learning capsules, propagation policies, and transfer telemetry.

Revision ID: 0010_learning_transfer
Revises: 0009_billing_and_license
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from typing import Any

revision = "0010_learning_transfer"
down_revision = "0009_billing_and_license"
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
        "knowledge_capsules",
        sa.Column("capsule_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("source_agent_id", sa.String(100), nullable=False),
        sa.Column("source_role", sa.String(200), nullable=False),
        sa.Column("source_domain_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("trigger_preconditions", sa.Text(), nullable=False),
        sa.Column("distilled_heuristic", sa.Text(), nullable=False),
        sa.Column("prohibited_contexts", JSONB, nullable=False, server_default="[]"),
        sa.Column("propagation_scope", sa.String(32), nullable=False),
        sa.Column("sensitivity_level", sa.String(32), nullable=False),
        sa.Column("source_workflow_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_crew_id", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("vector_id", sa.String(100), nullable=True),
        constraints=(
            sa.CheckConstraint("propagation_scope IN ('AGENT_PRIVATE','CREW_LOCAL','WORKFLOW_SCOPED','WORKSPACE_QUARANTINE','WORKSPACE_VERIFIED')", name="ck_capsule_scope"),
            sa.CheckConstraint("sensitivity_level IN ('PUBLIC','INTERNAL','CONFIDENTIAL_PII_STRIPPED')", name="ck_capsule_sensitivity"),
            sa.CheckConstraint("status IN ('active','quarantined')", name="ck_capsule_status"),
            sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_capsule_confidence"),
        ),
    )
    op.create_index("ix_capsule_source", "knowledge_capsules", ["tenant_id", "workspace_id", "source_agent_id"])
    _scoped_table(
        "learning_policies",
        sa.Column("source_agent_id", sa.String(100), nullable=False),
        sa.Column("target_agent_id", sa.String(100), nullable=False),
        sa.Column("propagation_scope", sa.String(32), nullable=False),
        sa.Column("allow_heuristics", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_code_patterns", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("require_human_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_domain_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("target_domain_tags", JSONB, nullable=False, server_default="[]"),
        constraints=(
            sa.UniqueConstraint("tenant_id", "workspace_id", "source_agent_id", "target_agent_id", name="uq_learning_policy_edge"),
            sa.CheckConstraint("propagation_scope IN ('AGENT_PRIVATE','CREW_LOCAL','WORKFLOW_SCOPED','WORKSPACE_QUARANTINE','WORKSPACE_VERIFIED')", name="ck_learning_policy_scope"),
        ),
    )
    _scoped_table(
        "transfer_application_logs",
        sa.Column("capsule_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_agent_id", sa.String(100), nullable=False),
        sa.Column("target_agent_id", sa.String(100), nullable=False),
        sa.Column("condition", sa.String(12), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("retry_and_error_turns", sa.Integer(), nullable=False),
        sa.Column("human_approval_rejected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("target_domain_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("tis_score", sa.Float(), nullable=True),
        constraints=(
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "capsule_id"], ["knowledge_capsules.tenant_id", "knowledge_capsules.workspace_id", "knowledge_capsules.id"], name="fk_transfer_application_logs_capsule_id_scope", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "run_id"], ["workflow_runs.tenant_id", "workflow_runs.workspace_id", "workflow_runs.id"], name="fk_transfer_application_logs_run_id_scope", ondelete="CASCADE"),
            sa.CheckConstraint("condition IN ('baseline','treatment')", name="ck_transfer_condition"),
            sa.CheckConstraint("retry_and_error_turns >= 0 AND token_count >= 0 AND latency_ms >= 0", name="ck_transfer_metrics_nonnegative"),
        ),
    )
    op.create_index("ix_transfer_pair", "transfer_application_logs", ["tenant_id", "workspace_id", "capsule_id", "target_agent_id", "condition"])
    _scoped_table(
        "transfer_circuit_breakers",
        sa.Column("capsule_id", UUID(as_uuid=True), nullable=False),
        sa.Column("target_agent_id", sa.String(100), nullable=False),
        sa.Column("target_domain_tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("tis_score", sa.Float(), nullable=False),
        sa.Column("application_count", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        constraints=(
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "capsule_id"], ["knowledge_capsules.tenant_id", "knowledge_capsules.workspace_id", "knowledge_capsules.id"], name="fk_transfer_circuit_breakers_capsule_id_scope", ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "workspace_id", "capsule_id", "target_agent_id", name="uq_transfer_breaker_pair"),
        ),
    )


def downgrade() -> None:
    for name in ("transfer_circuit_breakers", "transfer_application_logs", "learning_policies", "knowledge_capsules"):
        op.execute(f"DROP POLICY {name}_scope ON {name}")
        op.drop_table(name)
