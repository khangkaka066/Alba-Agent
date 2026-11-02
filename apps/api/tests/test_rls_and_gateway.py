from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.gateway_store import SqlGatewayStore
from app.models.scope import scoped_session
from nexus_model_gateway import CredentialCipher, GatewayRequest, LiteLLMRouter, ModelRate


async def _provision() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    url = os.environ["NEXUS_TEST_DATABASE_URL"]
    admin = create_async_engine(url)
    tenant_a, tenant_b, workspace_a, workspace_a2, workspace_b = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    async with admin.begin() as connection:
        await connection.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_app_test') THEN CREATE ROLE nexus_app_test LOGIN PASSWORD 'phase1-test' NOBYPASSRLS; END IF; END $$"))
        await connection.execute(text("GRANT nexus_app TO nexus_app_test"))
        await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:a, 'A'), (:b, 'B')"), {"a": tenant_a, "b": tenant_b})
        await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:wa, :a, 'A'), (:wa2, :a, 'A2'), (:wb, :b, 'B')"), {"wa": workspace_a, "wa2": workspace_a2, "a": tenant_a, "wb": workspace_b, "b": tenant_b})
        await connection.execute(text("INSERT INTO knowledge_bases (id, tenant_id, workspace_id, name, embedding_model) VALUES (:ka, :a, :wa, 'A', 'embedding'), (:ka2, :a, :wa2, 'A2', 'embedding'), (:kb, :b, :wb, 'B', 'embedding')"), {"ka": uuid4(), "ka2": uuid4(), "a": tenant_a, "wa": workspace_a, "wa2": workspace_a2, "kb": uuid4(), "b": tenant_b, "wb": workspace_b})
        await connection.execute(text("INSERT INTO tenant_budgets (tenant_id, remaining_usd, reserved_usd) VALUES (:a, 0.001, 0), (:b, 1, 0)"), {"a": tenant_a, "b": tenant_b})
    await admin.dispose()
    return tenant_a, tenant_b, workspace_a, workspace_a2, workspace_b


def _app_url() -> str:
    return make_url(os.environ["NEXUS_TEST_DATABASE_URL"]).set(
        username="nexus_app_test", password="phase1-test"
    ).render_as_string(hide_password=False)


def test_every_control_table_has_forced_rls_policy() -> None:
    if "NEXUS_TEST_DATABASE_URL" not in os.environ:
        pytest.skip("PostgreSQL test URL is not configured")

    async def check() -> None:
        engine = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                tables = await connection.execute(text("SELECT c.relname AS tablename, c.relrowsecurity AS rowsecurity, c.relforcerowsecurity AS forcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'"))
                policies = await connection.execute(text("SELECT tablename FROM pg_policies WHERE schemaname = 'public'"))
                policy_tables = set(policies.scalars())
                rows = tables.all()
                assert len(rows) == 34
                assert {"workflow_topology_versions", "workflow_evolution_policies"}.issubset({row.tablename for row in rows})
                assert "billing_webhook_events" in {row.tablename for row in rows}
                assert {"bot_messages", "routine_runs", "sandbox_computers"}.issubset({row.tablename for row in rows})
                assert {"knowledge_capsules", "learning_policies", "transfer_application_logs", "transfer_circuit_breakers"}.issubset({row.tablename for row in rows})
                assert all(row.rowsecurity and row.forcerowsecurity and row.tablename in policy_tables for row in rows)
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_rls_denies_other_tenant_and_unscoped_reads() -> None:
    if "NEXUS_TEST_DATABASE_URL" not in os.environ:
        pytest.skip("PostgreSQL test URL is not configured")

    async def check() -> None:
        tenant_a, tenant_b, workspace_a, workspace_a2, workspace_b = await _provision()
        engine = create_async_engine(_app_url())
        try:
            async with engine.connect() as conn:
                unscoped_result = await conn.execute(text("SELECT count(*) FROM knowledge_bases"))
                assert unscoped_result.scalar_one() == 0
            async with scoped_session(engine, tenant_a, workspace_a) as session:
                visible_bases = await session.execute(text("SELECT name FROM knowledge_bases"))
                assert visible_bases.scalars().all() == ["A"]
                visible_tenants = await session.execute(text("SELECT count(*) FROM tenants"))
                assert visible_tenants.scalar_one() == 1
                visible_budgets = await session.execute(text("SELECT count(*) FROM tenant_budgets"))
                assert visible_budgets.scalar_one() == 1
            async with scoped_session(engine, tenant_b, workspace_b) as session:
                other_bases = await session.execute(text("SELECT name FROM knowledge_bases"))
                assert other_bases.scalars().all() == ["B"]
            async with scoped_session(engine, tenant_a, workspace_a2) as session:
                sibling_bases = await session.execute(text("SELECT name FROM knowledge_bases"))
                assert sibling_bases.scalars().all() == ["A2"]
            with pytest.raises(DBAPIError):
                async with scoped_session(engine, tenant_a, workspace_a) as session:
                    await session.execute(
                        text("INSERT INTO knowledge_bases (id, tenant_id, workspace_id, name, embedding_model) VALUES (:id, :tenant, :workspace, 'escape', 'embedding')"),
                        {"id": uuid4(), "tenant": tenant_b, "workspace": workspace_b},
                    )
            with pytest.raises(DBAPIError):
                async with scoped_session(engine, tenant_a, workspace_a) as session:
                    await session.execute(
                        text("INSERT INTO knowledge_bases (id, tenant_id, workspace_id, name, embedding_model) VALUES (:id, :tenant, :workspace, 'escape', 'embedding')"),
                        {"id": uuid4(), "tenant": tenant_a, "workspace": workspace_a2},
                    )
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_gateway_cost_budget_and_encrypted_byok() -> None:
    if "NEXUS_TEST_DATABASE_URL" not in os.environ:
        pytest.skip("PostgreSQL test URL is not configured")

    async def check() -> None:
        tenant_a, _, workspace_a, _, _ = await _provision()
        engine = create_async_engine(_app_url())
        cipher = CredentialCipher(b"x" * 32)
        store = SqlGatewayStore(engine, cipher)
        calls: list[dict[str, object]] = []

        async def completion(**kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"usage": {"prompt_tokens": 100, "completion_tokens": 50}, "choices": [{"message": {"content": "done"}}]}

        router = LiteLLMRouter(
            store,
            {("openai", "approved-model"): ModelRate(Decimal("2"), Decimal("4"))},
            completion=completion,
            token_counter=lambda _model, _messages: 100,
        )
        try:
            request = GatewayRequest(tenant_a, workspace_a, "openai", "approved-model", ({"role": "user", "content": "hi"},), 200, 100, "platform", "reviewer")
            result = await router.complete(request)
            assert result.content == "done"
            assert result.usage.total_cost_usd == Decimal("0.00040000")
            assert result.usage.prompt_tokens == 100 and result.usage.completion_tokens == 50
            assert result.usage.latency_ms >= 0
            async with scoped_session(engine, tenant_a, workspace_a) as session:
                remaining = (await session.execute(text("SELECT remaining_usd FROM tenant_budgets WHERE tenant_id = :id"), {"id": tenant_a})).scalar_one()
                assert remaining == Decimal("0.00060000")
                assert (await session.execute(text("SELECT count(*) FROM token_usage_logs"))).scalar_one() == 1
            expensive = GatewayRequest(tenant_a, workspace_a, "openai", "approved-model", ({"role": "user", "content": "hi"},), 1000, 1000, "platform", "reviewer")
            with pytest.raises(Exception, match="budget"):
                await router.complete(expensive)
            assert len(calls) == 1
            credential_id = await store.save_credential(tenant_a, workspace_a, "openai", "personal", "secret-key")
            async with scoped_session(engine, tenant_a, workspace_a) as session:
                encrypted = (await session.execute(text("SELECT encrypted_key FROM model_credentials WHERE id = :id"), {"id": credential_id})).scalar_one()
                assert "secret-key" not in encrypted
            with pytest.raises(InvalidTag):
                cipher.decrypt(encrypted, uuid4(), workspace_a, "openai")
            byok = GatewayRequest(tenant_a, workspace_a, "openai", "approved-model", ({"role": "user", "content": "hi"},), 200, 100, "byok", "reviewer", credential_id=credential_id)
            await router.complete(byok)
            assert calls[-1]["api_key"] == "secret-key"
            async with scoped_session(engine, tenant_a, workspace_a) as session:
                remaining_after_byok = (await session.execute(text("SELECT remaining_usd FROM tenant_budgets WHERE tenant_id = :id"), {"id": tenant_a})).scalar_one()
                assert remaining_after_byok == Decimal("0.00060000")
                assert (await session.execute(text("SELECT count(*) FROM token_usage_logs"))).scalar_one() == 2

            async def over_limit_completion(**_kwargs: object) -> dict[str, object]:
                return {"usage": {"prompt_tokens": 1000, "completion_tokens": 1000}, "choices": [{"message": {"content": "over limit"}}]}

            over_limit_router = LiteLLMRouter(
                store,
                {("openai", "approved-model"): ModelRate(Decimal("2"), Decimal("4"))},
                completion=over_limit_completion,
                token_counter=lambda _model, _messages: 100,
            )
            over_limit_request = GatewayRequest(tenant_a, workspace_a, "openai", "approved-model", ({"role": "user", "content": "hi"},), 100, 50, "platform", "reviewer")
            over_limit_result = await over_limit_router.complete(over_limit_request)
            assert over_limit_result.usage_limit_exceeded
            assert over_limit_result.usage.total_cost_usd == Decimal("0.00600000")
            async with scoped_session(engine, tenant_a, workspace_a) as session:
                remaining_and_overage = (await session.execute(text("SELECT remaining_usd, overage_usd FROM tenant_budgets WHERE tenant_id = :id"), {"id": tenant_a})).one()
                assert remaining_and_overage == (Decimal("0"), Decimal("0.00540000"))
                assert (await session.execute(text("SELECT count(*) FROM token_usage_logs"))).scalar_one() == 3
            with pytest.raises(Exception, match="budget"):
                await router.complete(request)
        finally:
            await engine.dispose()

    asyncio.run(check())
