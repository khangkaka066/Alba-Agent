"""Stored subscription credentials resolve through PostgreSQL row-level security and are logged as plan-included."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import ModelCredential, TokenUsageLog
from app.models.gateway_store import SqlGatewayStore
from app.models.scope import scoped_session
from nexus_model_gateway import CredentialCipher, UsageRecord
from nexus_model_gateway.router import METERED, SUBSCRIPTION_INCLUDED
from nexus_model_gateway.subscription_connectors import CopilotTokenBroker


def test_subscription_credentials_resolve_and_usage_records_billing_mode() -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL with the runtime role is required")

    def session_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token": "tid=copilot-session", "expires_at": 4_102_444_800, "endpoints": {"api": "https://api.githubcopilot.com"}})

    async def check() -> None:
        tenant, workspace = uuid4(), uuid4()
        admin = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        app_engine = create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        cipher = CredentialCipher(b"k" * 32)
        broker = CopilotTokenBroker(client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(session_handler)))
        store = SqlGatewayStore(app_engine, cipher, broker)

        async def add(provider: str, preset: str, secret: str, base_url: str | None, settings: dict[str, object], default: bool) -> UUID:
            async with scoped_session(app_engine, tenant, workspace) as session:
                row = ModelCredential(id=uuid4(), tenant_id=tenant, workspace_id=workspace, provider=provider, name=preset, preset_id=preset,
                                      encrypted_key=cipher.encrypt(secret, tenant, workspace, provider), key_version=1, base_url=base_url,
                                      status="connected", is_default=default, settings=settings)
                session.add(row)
                await session.flush()
                return row.id

        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Plans')"), {"id": tenant})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Plans')"), {"id": workspace, "t": tenant})

            claude_id = await add("anthropic", "claude_subscription", "sk-ant-oat01-token", "https://api.anthropic.com",
                                  {"billing_mode": SUBSCRIPTION_INCLUDED, "auth_kind": "oauth_token", "plan": "max"}, True)
            claude = await store.resolve_default_credential(tenant, workspace, "anthropic")
            assert claude is not None and claude.api_key == "sk-ant-oat01-token" and claude.billing_mode == SUBSCRIPTION_INCLUDED
            assert claude.wire == "native" and claude.headers["Authorization"] == "Bearer sk-ant-oat01-token"
            by_id = await store.resolve_credential(tenant, workspace, claude_id, "anthropic")
            assert by_id.api_key == claude.api_key
            with pytest.raises(LookupError):
                await store.resolve_credential(tenant, workspace, claude_id, "openai")  # a Claude plan does not serve OpenAI models

            # a metered key for another provider keeps its price; defaults are per provider
            await add("openai", "openai", "sk-metered", "https://api.openai.com/v1", {}, True)
            metered = await store.resolve_default_credential(tenant, workspace, "openai")
            assert metered is not None and metered.billing_mode == METERED and not metered.headers
            assert (await store.resolve_default_credential(tenant, workspace, "anthropic")) == claude

            # Copilot serves every model family over the OpenAI format with a freshly minted session token
            await add("openai", "github_copilot", CredentialCipher.encode_fields({"oauth_token": "gho_user"}), "https://api.githubcopilot.com", {"billing_mode": SUBSCRIPTION_INCLUDED}, False)
            async with scoped_session(app_engine, tenant, workspace) as session:
                for row in (await session.scalars(select(ModelCredential))).all():
                    row.is_default = row.preset_id == "github_copilot"
            copilot = await store.resolve_default_credential(tenant, workspace, "gemini")
            assert copilot is not None and copilot.api_key == "tid=copilot-session" and copilot.wire == "openai"
            assert copilot.billing_mode == SUBSCRIPTION_INCLUDED and copilot.headers["Copilot-Integration-Id"] == "vscode-chat"

            # usage keeps the billing mode; plan usage is not charged to the managed budget
            await store.finalize(Decimal("0"), UsageRecord(tenant, workspace, None, None, "agent", "anthropic", "claude-sonnet-4-6", 10, 5, Decimal("0"), 120,
                                                           billing_mode=SUBSCRIPTION_INCLUDED), False)
            async with scoped_session(app_engine, tenant, workspace) as session:
                log = await session.scalar(select(TokenUsageLog))
                assert log is not None and log.billing_mode == SUBSCRIPTION_INCLUDED and log.total_cost_usd == 0 and log.managed_charge is False

            async with scoped_session(app_engine, uuid4(), uuid4()) as session:
                assert (await session.scalars(select(ModelCredential))).all() == []
            assert await store.resolve_default_credential(uuid4(), uuid4(), "anthropic") is None
        finally:
            await admin.dispose()
            await app_engine.dispose()

    asyncio.run(check())
