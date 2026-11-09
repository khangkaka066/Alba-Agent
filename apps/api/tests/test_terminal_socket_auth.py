"""Verify signed-token stdin and immediate role-revocation handling over a real ASGI WebSocket."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth import context as auth
from app.routers import sandboxes
from nexus_computer_sandbox import ComputerAccess


def test_terminal_socket_authenticates_and_rechecks_builder_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_SECRET_KEY", "terminal-socket-verification-secret-32-bytes")
    context = auth.TenantContext(uuid4(), uuid4(), uuid4(), "builder")
    computer = uuid4()
    scope = ComputerAccess(context.tenant_id, context.workspace_id, run_id=uuid4())
    current_role: list[auth.Role] = ["builder"]
    received: list[bytes] = []

    async def membership(_engine: Any, tenant: UUID, workspace: UUID, user: UUID) -> auth.Role:
        assert (tenant, workspace, user) == (context.tenant_id, context.workspace_id, context.user_id)
        return current_role[0]

    async def computer_context(_request: Request, caller: auth.TenantContext, requested: UUID) -> Any:
        assert caller == context and requested == computer
        return scope, SimpleNamespace()

    class Terminal:
        async def input(self, access: ComputerAccess, requested: UUID, data: bytes, process_id: str | None) -> None:
            assert access == scope and requested == computer and process_id is None
            received.append(data)

    monkeypatch.setattr(auth, "_membership", membership)
    monkeypatch.setattr(sandboxes, "_computer_context", computer_context)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=object(), interactive=Terminal())
    app.include_router(sandboxes.router)
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/sandboxes/{computer}/terminal/input", headers={"origin": "http://testserver"}) as socket:
            socket.send_json({"token": auth.issue_access_token(context)})
            assert socket.receive_json() == {"ready": True}
            socket.send_json({"data": "yes\n"})
            assert socket.receive_json() == {"ok": True}
            current_role[0] = "viewer"
            socket.send_json({"data": "forbidden\n"})
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1008
    assert received == [b"yes\n"]


def test_terminal_socket_refuses_foreign_origins_before_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(sandboxes.router)
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/sandboxes/{uuid4()}/terminal/input", headers={"origin": "https://untrusted.invalid"}) as socket:
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1008
