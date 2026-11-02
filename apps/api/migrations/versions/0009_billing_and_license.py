"""Tenant subscriptions and idempotent billing webhook ledger.

Revision ID: 0009_billing_and_license
Revises: 0008_provider_settings
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009_billing_and_license"
down_revision = "0008_provider_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("plan", sa.String(16), server_default="FREE", nullable=False))
    op.add_column("tenants", sa.Column("billing_provider", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("billing_customer_id", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("billing_subscription_id", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_tenants_plan", "tenants", "plan IN ('FREE','PRO','ENTERPRISE')")
    op.add_column("token_usage_logs", sa.Column("managed_charge", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_table(
        "billing_webhook_events",
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "workspace_id"], ["workspaces.tenant_id", "workspaces.id"], ondelete="CASCADE", name="fk_billing_webhook_events_workspace_scope"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "id", name="uq_billing_webhook_events_scope_id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "provider", "event_id", name="uq_billing_event_provider_id"),
    )
    op.create_index("ix_billing_webhook_events_tenant_id", "billing_webhook_events", ["tenant_id"])
    op.create_index("ix_billing_webhook_events_workspace_id", "billing_webhook_events", ["workspace_id"])
    tenant = "NULLIF(current_setting('nexus.tenant_id', true), '')::uuid"
    workspace = "NULLIF(current_setting('nexus.workspace_id', true), '')::uuid"
    op.execute("ALTER TABLE billing_webhook_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_webhook_events FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY billing_webhook_events_scope ON billing_webhook_events USING (tenant_id = {tenant} AND workspace_id = {workspace}) WITH CHECK (tenant_id = {tenant} AND workspace_id = {workspace})")
    op.execute("GRANT SELECT, INSERT ON billing_webhook_events TO nexus_app")
    op.execute("""
        CREATE FUNCTION nexus_tenant_resource_count(resource_name text, target_tenant uuid)
        RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
        DECLARE result bigint;
        BEGIN
            IF target_tenant IS DISTINCT FROM NULLIF(current_setting('nexus.tenant_id', true), '')::uuid
               OR NOT EXISTS (SELECT 1 FROM workspaces WHERE tenant_id = target_tenant AND id = NULLIF(current_setting('nexus.workspace_id', true), '')::uuid) THEN
                RAISE EXCEPTION 'tenant scope mismatch';
            END IF;
            IF resource_name = 'workspaces' THEN SELECT count(*) INTO result FROM workspaces WHERE tenant_id = target_tenant;
            ELSIF resource_name = 'persistent_bots' THEN SELECT count(*) INTO result FROM persistent_bots WHERE tenant_id = target_tenant;
            ELSE RAISE EXCEPTION 'unsupported resource count'; END IF;
            RETURN result;
        END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION nexus_tenant_resource_count(text, uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION nexus_tenant_resource_count(text, uuid) TO nexus_runtime")
    op.execute("""
        CREATE FUNCTION nexus_create_workspace(target_tenant uuid, source_workspace uuid, new_workspace uuid, workspace_name text)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
        BEGIN
            IF target_tenant IS DISTINCT FROM NULLIF(current_setting('nexus.tenant_id', true), '')::uuid
               OR source_workspace IS DISTINCT FROM NULLIF(current_setting('nexus.workspace_id', true), '')::uuid
               OR NOT EXISTS (SELECT 1 FROM workspaces WHERE tenant_id = target_tenant AND id = source_workspace) THEN
                RAISE EXCEPTION 'tenant scope mismatch';
            END IF;
            INSERT INTO workspaces(id, tenant_id, name) VALUES(new_workspace, target_tenant, workspace_name);
        END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION nexus_create_workspace(uuid, uuid, uuid, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION nexus_create_workspace(uuid, uuid, uuid, text) TO nexus_runtime")


def downgrade() -> None:
    op.execute("DROP FUNCTION nexus_create_workspace(uuid, uuid, uuid, text)")
    op.execute("DROP FUNCTION nexus_tenant_resource_count(text, uuid)")
    op.execute("DROP POLICY billing_webhook_events_scope ON billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_workspace_id", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_tenant_id", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.drop_constraint("ck_tenants_plan", "tenants", type_="check")
    op.drop_column("token_usage_logs", "managed_charge")
    for name in ("billing_period_end", "billing_subscription_id", "billing_customer_id", "billing_provider", "plan"):
        op.drop_column("tenants", name)
