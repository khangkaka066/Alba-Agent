"""Public account creation and password login against an isolated test tenant."""

from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.router import router
from nexus_plugins.support.llm_service import has_managed_model_credit as _has_managed_model_credit


class MemoryCounters:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self.values and seconds > 0


def test_public_signup_requires_operator_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_PUBLIC_SIGNUP_ENABLED", "false")
    app = FastAPI()
    app.include_router(router)

    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            options = await client.get("/api/v1/auth/signup-options")
            assert options.json() == {"public_signup_enabled": False}
            result = await client.post("/api/v1/auth/signup", json={
                "tenant_name": "Test", "workspace_name": "Test", "display_name": "Test",
                "email": "test@example.invalid", "password": "a-long-test-password",
            })
            assert result.status_code == 403

    asyncio.run(check())


def test_public_signup_login_and_zero_credit(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.environ.get("NEXUS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("A migrated PostgreSQL test database is required")
    monkeypatch.setenv("NEXUS_PUBLIC_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("NEXUS_SETUP_DATABASE_URL", database_url)
    monkeypatch.setenv("NEXUS_API_KEY_PEPPER", "public-signup-test-pepper-with-32-bytes")
    monkeypatch.setenv("NEXUS_SECRET_KEY", "public-signup-test-secret-with-32-bytes")
    app = FastAPI()
    app.include_router(router)
    app.state.services = type("Services", (), {"redis": MemoryCounters()})()
    email = f"signup-{uuid4().hex}@example.invalid"
    password = "a-long-test-password"
    tenant_id: UUID | None = None

    async def check() -> None:
        nonlocal tenant_id
        engine = create_async_engine(database_url)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                body = {"tenant_name": "Signup test", "workspace_name": "Signup test", "display_name": "Owner",
                        "email": email, "password": password}
                created = await client.post("/api/v1/auth/signup", json=body)
                assert created.status_code == 201, created.text
                tenant_id = UUID(created.json()["tenant_id"])
                login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
                assert login.status_code == 200, login.text
                assert login.json()["tenant_id"] == str(tenant_id)
                assert (await client.post("/api/v1/auth/signup", json=body)).status_code == 409
                assert (await client.post("/api/v1/auth/signup", json=body)).status_code == 409
                assert (await client.post("/api/v1/auth/signup", json=body)).status_code == 429
                assert (await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})).status_code == 401
                async with engine.connect() as connection:
                    credit = await connection.scalar(text("SELECT remaining_usd FROM tenant_budgets WHERE tenant_id = :id"), {"id": tenant_id})
                assert credit == 0
                assert not await _has_managed_model_credit(engine, tenant_id, UUID(created.json()["workspace_id"]))
        finally:
            if tenant_id is not None:
                async with engine.begin() as connection:
                    await connection.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})
            await engine.dispose()

    asyncio.run(check())
