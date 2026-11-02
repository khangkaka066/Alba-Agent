"""Persisted task conversations, and the structured failure of a run.

Revision ID: 0016_task_conversations
Revises: 0015_billing_mode
"""
from typing import Any
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0016_task_conversations"
down_revision = "0015_billing_mode"
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
        "task_conversations",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _scoped(
        "conversation_messages",
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
        sa.Column("meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        constraints=(
            sa.ForeignKeyConstraint(["tenant_id", "workspace_id", "conversation_id"], ["task_conversations.tenant_id", "task_conversations.workspace_id", "task_conversations.id"],
                                    ondelete="CASCADE", name="fk_conversation_messages_conversation_id_scope"),
            sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_message_sequence"),
            sa.CheckConstraint("role IN ('user','team','note')", name="ck_conversation_message_role"),
        ),
    )
    op.create_index("ix_conversation_messages_run", "conversation_messages", ["tenant_id", "workspace_id", "run_id"])
    op.add_column("workflow_runs", sa.Column("failure", JSONB(), nullable=True))
    # Conversations for the runs that already exist: one thread per run, the original request then the team card.
    op.execute("""
        INSERT INTO task_conversations (id, tenant_id, workspace_id, title, created_at, updated_at)
        SELECT r.id, r.tenant_id, r.workspace_id, left(COALESCE(NULLIF(r.input_data->>'task', ''), w.name), 200), r.created_at, COALESCE(r.finished_at, r.created_at)
        FROM workflow_runs r JOIN workflows w ON w.tenant_id = r.tenant_id AND w.workspace_id = r.workspace_id AND w.id = r.workflow_id
        """)
    op.execute("""
        INSERT INTO conversation_messages (id, tenant_id, workspace_id, conversation_id, sequence, role, text, run_id, workflow_id, meta, created_at)
        SELECT gen_random_uuid(), r.tenant_id, r.workspace_id, r.id, 1, 'user', left(COALESCE(NULLIF(r.input_data->>'task', ''), w.name), 4000), NULL, NULL, '{}'::jsonb, r.created_at
        FROM workflow_runs r JOIN workflows w ON w.tenant_id = r.tenant_id AND w.workspace_id = r.workspace_id AND w.id = r.workflow_id
        """)
    op.execute("""
        INSERT INTO conversation_messages (id, tenant_id, workspace_id, conversation_id, sequence, role, text, run_id, workflow_id, meta, created_at)
        SELECT gen_random_uuid(), r.tenant_id, r.workspace_id, r.id, 2, 'team', left(w.name, 4000), r.id, r.workflow_id, '{}'::jsonb, r.created_at
        FROM workflow_runs r JOIN workflows w ON w.tenant_id = r.tenant_id AND w.workspace_id = r.workspace_id AND w.id = r.workflow_id
        """)


def downgrade() -> None:
    op.drop_column("workflow_runs", "failure")
    op.drop_table("conversation_messages")
    op.drop_table("task_conversations")
