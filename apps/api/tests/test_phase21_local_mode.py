"""Local single-user mode: the app opens without sign-in, and only when the server says so."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import router as auth_router
from app.auth.context import TenantContext, decode_access_token
from app.auth.local import LOCAL_EMAIL
from app.models import ModelCredential, Tenant, User
from app.models.scope import scoped_session
from app.routers import providers
from nexus_model_gateway import CredentialCipher


def test_local_session_is_refused_unless_the_server_enables_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_MODE", raising=False)
    monkeypatch.setenv("NEXUS_SETUP_DATABASE_URL", "postgresql+asyncpg://unused")
    assert asyncio.run(auth_router.local_mode()).enabled is False
    with pytest.raises(HTTPException) as refused:
        asyncio.run(auth_router.local_session())
    assert refused.value.status_code == 403
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "true")
    assert asyncio.run(auth_router.local_mode()).enabled is True


def _database_urls() -> tuple[str, str]:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL with the runtime role is required")
    return os.environ["NEXUS_TEST_DATABASE_URL"], os.environ["NEXUS_TEST_APP_DATABASE_URL"]


def test_local_workspace_is_seeded_once_and_every_session_lands_in_it(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url, _ = _database_urls()
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "true")
    monkeypatch.setenv("NEXUS_SETUP_DATABASE_URL", admin_url)

    async def check() -> None:
        first, second = await auth_router.local_session(), await auth_router.local_session()
        assert (first.tenant_id, first.workspace_id, first.user_id) == (second.tenant_id, second.workspace_id, second.user_id)
        tenant, workspace, user = decode_access_token(first.access_token)
        assert (tenant, workspace, user) == (first.tenant_id, first.workspace_id, first.user_id)
        engine = create_async_engine(admin_url)
        try:
            async with engine.connect() as connection:
                assert await connection.scalar(select(func.count()).select_from(User).where(User.email == LOCAL_EMAIL)) == 1
                assert await connection.scalar(select(Tenant.plan).where(Tenant.id == first.tenant_id)) == "ENTERPRISE"
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_ai_status_reports_a_workspace_key_a_server_key_or_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url, app_url = _database_urls()
    for name in ("NEXUS_OPENAI_API_KEY", "NEXUS_ANTHROPIC_API_KEY", "NEXUS_GEMINI_API_KEY", "NEXUS_DEEPSEEK_API_KEY", "NEXUS_OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    async def check() -> None:
        tenant, workspace = uuid4(), uuid4()
        admin, app_engine = create_async_engine(admin_url), create_async_engine(app_url)
        request = cast(Request, SimpleNamespace(app=cast(FastAPI, SimpleNamespace(state=SimpleNamespace(services=SimpleNamespace(engine=app_engine))))))
        context = TenantContext(tenant, workspace, uuid4(), "owner")
        cipher = CredentialCipher(b"k" * 32)
        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Status')"), {"id": tenant})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Status')"), {"id": workspace, "t": tenant})
                await connection.execute(text("INSERT INTO tenant_budgets (tenant_id, remaining_usd, reserved_usd, overage_usd) VALUES (:t, :usd, 0, 0)"), {"t": tenant, "usd": Decimal("5")})
            assert (await providers.ai_status(request, context))["ready"] is False

            monkeypatch.setenv("NEXUS_OPENAI_API_KEY", "sk-server")
            server = await providers.ai_status(request, context)
            assert (server["ready"], server["source"], server["model"]) == (True, "platform", "gpt-4.1-mini")

            async with scoped_session(app_engine, tenant, workspace) as session:
                session.add(ModelCredential(id=uuid4(), tenant_id=tenant, workspace_id=workspace, provider="anthropic", name="claude_subscription",
                                            preset_id="claude_subscription", encrypted_key=cipher.encrypt("t", tenant, workspace, "anthropic"), key_version=1,
                                            status="connected", is_default=True, available_models=["claude-sonnet-4-6"], default_models={}))
                session.add(ModelCredential(id=uuid4(), tenant_id=tenant, workspace_id=workspace, provider="tiktok", name="tiktok", preset_id="tiktok",
                                            encrypted_key=cipher.encrypt("t", tenant, workspace, "tiktok"), key_version=1, status="connected", available_models=["x"]))
            workspace_status = await providers.ai_status(request, context)
            assert (workspace_status["ready"], workspace_status["source"], workspace_status["model"]) == (True, "workspace", "claude-sonnet-4-6")
        finally:
            await admin.dispose()
            await app_engine.dispose()

    asyncio.run(check())


def test_channel_presets_exist_and_are_not_model_providers() -> None:
    from nexus_model_gateway.provider_presets import PRESETS_BY_ID

    for preset_id in ("tiktok", "facebook", "youtube"):
        preset = PRESETS_BY_ID[preset_id]
        assert preset.category == "channel" and any(field.secret for field in preset.auth_fields)
        assert preset.category not in providers.MODEL_CATEGORIES


def test_chat_models_lists_what_the_workspace_can_run_and_names_them_the_way_the_architect_expects(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url, app_url = _database_urls()
    for name in ("NEXUS_OPENAI_API_KEY", "NEXUS_ANTHROPIC_API_KEY", "NEXUS_GEMINI_API_KEY", "NEXUS_DEEPSEEK_API_KEY", "NEXUS_OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    async def check() -> None:
        tenant, workspace = uuid4(), uuid4()
        admin, app_engine = create_async_engine(admin_url), create_async_engine(app_url)
        request = cast(Request, SimpleNamespace(app=cast(FastAPI, SimpleNamespace(state=SimpleNamespace(services=SimpleNamespace(engine=app_engine))))))
        context = TenantContext(tenant, workspace, uuid4(), "owner")
        cipher = CredentialCipher(b"k" * 32)
        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Models')"), {"id": tenant})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Models')"), {"id": workspace, "t": tenant})
                await connection.execute(text("INSERT INTO tenant_budgets (tenant_id, remaining_usd, reserved_usd, overage_usd) VALUES (:t, :usd, 0, 0)"), {"t": tenant, "usd": Decimal("5")})
            nothing = await providers.chat_models(request, context)
            assert nothing["models"] == [] and nothing["default"] is None
            offered = cast(list[dict[str, object]], nothing["suggested"])
            assert {"openai/gpt-5.4", "anthropic/claude-opus-4-6", "gemini/gemini-2.5-pro", "deepseek/deepseek-chat"} <= {str(item["id"]) for item in offered}
            assert not any(item["connected"] for item in offered), "nothing is connected, so no flagship model is usable yet"

            monkeypatch.setenv("NEXUS_OPENAI_API_KEY", "sk-server")
            monkeypatch.setenv("NEXUS_ANTHROPIC_API_KEY", "sk-ant")
            platform = await providers.chat_models(request, context)
            ids = [str(item["id"]) for item in cast(list[dict[str, object]], platform["models"])]
            assert {"openai/gpt-4.1-mini", "openai/gpt-4o", "anthropic/claude-sonnet-4-6"} <= set(ids) and platform["default"] == "openai/gpt-4.1-mini"
            assert all(not any(part in identifier for part in ("embed", "whisper", "tts")) for identifier in ids)
            connected = {str(item["id"]): item["connected"] for item in cast(list[dict[str, object]], platform["suggested"])}
            assert connected["openai/gpt-5.4"] is True and connected["gemini/gemini-2.5-pro"] is False and connected["deepseek/deepseek-chat"] is False
            assert "anthropic/claude-opus-4-6" in ids and "anthropic/claude-opus-4-6" not in connected  # already listed, so not repeated as a suggestion

            async with scoped_session(app_engine, tenant, workspace) as session:
                session.add(ModelCredential(id=uuid4(), tenant_id=tenant, workspace_id=workspace, provider="ollama", name="ollama", preset_id="ollama",
                                            encrypted_key=cipher.encrypt("t", tenant, workspace, "ollama"), key_version=1, status="connected", is_default=True,
                                            available_models=["llama3.1:8b", "nomic-embed-text"], default_models={}))
                session.add(ModelCredential(id=uuid4(), tenant_id=tenant, workspace_id=workspace, provider="tiktok", name="tiktok", preset_id="tiktok",
                                            encrypted_key=cipher.encrypt("t", tenant, workspace, "tiktok"), key_version=1, status="connected", available_models=["x"]))
            mixed = await providers.chat_models(request, context)
            by_id = {item["id"]: item for item in cast(list[dict[str, object]], mixed["models"])}
            assert mixed["default"] == "ollama/llama3.1:8b"  # a model detected on this machine wins as the default
            assert by_id["ollama/llama3.1:8b"]["local"] is True and "ollama/nomic-embed-text" not in by_id
            assert "openai/gpt-4o" in by_id and not any(str(key).startswith("tiktok/") for key in by_id)
        finally:
            await admin.dispose()
            await app_engine.dispose()

    asyncio.run(check())
