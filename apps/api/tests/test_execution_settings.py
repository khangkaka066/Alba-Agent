"""Execution controls are scoped, authenticated and enforced before managed tools act."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import ValidationError

from app.auth.context import TenantContext
from app.execution_settings import ExecutionSettings
from app.routers import execution_settings as routes
from nexus_builtin_tools import BuiltinToolRegistry, ToolContext


def test_domain_rules_normalize_and_deny_takes_precedence() -> None:
    policy = ExecutionSettings(allowed_domains=["HTTPS://Example.COM/path", "*.example.org", "example.com"], denied_domains=["blocked.example.org", "bücher.example"])
    assert policy.allowed_domains == ["example.com", "*.example.org"]
    assert policy.allows_url("https://EXAMPLE.COM./ok")
    assert policy.allows_url("https://a.example.org/ok")
    for url in ["https://blocked.example.org", "https://example.org", "https://example.com.evil.test", "https://other.test", "file:///tmp/private"]:
        assert not policy.allows_url(url), url
    denied = ExecutionSettings(denied_domains=["bücher.example"])
    assert not denied.allows_url("https://bücher.example/path")
    assert not denied.allows_url("https://xn--bcher-kva.example/path")
    with pytest.raises(PermissionError):
        denied.check_tool("web_scraper", {"arguments": {"url": "HTTPS://bücher.example/path"}})
    for domain in ["https://user:secret@example.com", "../example.com", "*.bad..test", "example.com:443"]:
        with pytest.raises(ValidationError):
            ExecutionSettings(denied_domains=[domain])
    with pytest.raises(ValidationError):
        ExecutionSettings.model_validate({"permission_preset": "bypass"})


def test_authorization_and_disabled_tool_checks_precede_any_side_effect(tmp_path: Path) -> None:
    calls: list[str] = []
    async def authorize(tool: str, payload: dict[str, Any]) -> None:
        calls.append("authorize")
        raise PermissionError("Approval required")
    async def shell(command: str, timeout: int) -> str:
        calls.append("executed")
        return "done"
    context = ToolContext("tenant", "workspace", "run", tmp_path, shell=shell, authorize_tool=authorize)
    registry = BuiltinToolRegistry(context)
    with pytest.raises(PermissionError, match="Approval required"):
        asyncio.run(registry.run("sandbox_shell", {"command": "echo test"}))
    assert calls == ["authorize"]
    context.enabled_ids = frozenset()
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(registry.run("sandbox_shell", {"command": "echo test"}))
    assert calls == ["authorize"]


def test_settings_api_preserves_workspace_scope_audit_and_role_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, bytes] = {}
    audits: list[Any] = []
    scope = TenantContext(uuid4(), uuid4(), uuid4(), "owner")
    class Redis:
        async def get(self, key: str) -> bytes | None:
            return saved.get(key)
        async def set(self, key: str, value: str) -> None:
            saved[key] = value.encode()
    services = SimpleNamespace(redis=Redis(), engine=object())
    @asynccontextmanager
    async def session(engine: object, tenant: object, workspace: object) -> AsyncIterator[Any]:
        assert tenant == scope.tenant_id and workspace == scope.workspace_id
        yield SimpleNamespace(add=audits.append)
    monkeypatch.setattr(routes, "get_services", lambda request: services)
    monkeypatch.setattr(routes, "scoped_session", session)
    def app(authenticated: bool) -> FastAPI:
        result = FastAPI()
        result.state.services = services
        result.include_router(routes.router)
        if authenticated:
            for route in result.routes:
                if isinstance(route, APIRoute):
                    # Preserve require_role; only replace the authenticated identity dependency.
                    for dependency in route.dependant.dependencies:
                        for identity in dependency.dependencies:
                            if identity.call is not None:
                                result.dependency_overrides[identity.call] = lambda: scope
        return result
    async def check() -> None:
        nonlocal scope
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app(False)), base_url="http://nexus.test") as guest:
            assert (await guest.get("/api/v1/settings/execution")).status_code in {401,403}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app(True)), base_url="http://nexus.test") as client:
            assert (await client.get("/api/v1/settings/execution")).json()["permission_preset"] == "auto"
            response = await client.put("/api/v1/settings/execution", json={"permission_preset": "strict", "denied_domains": ["example.com"]})
            assert response.status_code == 200, response.text
            assert (await client.get("/api/v1/settings/execution")).json()["denied_domains"] == ["example.com"]
            assert len(audits) == 1 and audits[0].workspace_id == scope.workspace_id and audits[0].actor_id == scope.user_id
            scope = TenantContext(scope.tenant_id, uuid4(), scope.user_id, "owner")
            assert (await client.get("/api/v1/settings/execution")).json()["permission_preset"] == "auto"
            scope = TenantContext(scope.tenant_id, scope.workspace_id, scope.user_id, "viewer")
            assert (await client.put("/api/v1/settings/execution", json={"permission_preset": "auto"})).status_code == 403
            assert len(audits) == 1
    asyncio.run(check())
