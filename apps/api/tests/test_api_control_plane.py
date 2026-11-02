"""Authenticated REST, workflow worker, approval, and SSE integration coverage."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.auth.context import hash_password
from app.models import ApprovalRequest, AuditLog, BotRoutine, KnowledgeBase, PersistentBot, Tenant, User, Workflow, WorkflowRun, Workspace, WorkspaceMember
from app.models.scope import scoped_session
from app.services import AppServices
from app.workers.jobs import CeleryDispatcher, WorkerExecutor
from autogen_bridge.sandbox_team import AutoGenSandboxRunner
from nexus_computer_sandbox import ComputerSandboxSupervisor, DockerSandboxProvider
from nexus_core_schema.models import RuntimeEventType
from callbacks.event_bus import RuntimeEventEmitter
from app.main import create_app


class InlineDispatcher:
    def __init__(self) -> None:
        self.services: AppServices | None = None

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        assert self.services is not None
        await WorkerExecutor(self.services).workflow(tenant_id, workspace_id, run_id)

    async def bot_turn(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID, thread_id: UUID, content: str) -> None:
        raise AssertionError("Unexpected bot task")

    async def routine(self, tenant_id: UUID, workspace_id: UUID, routine_run_id: UUID) -> None:
        raise AssertionError("Unexpected routine task")


class NoopSandboxRunner:
    async def run(self, task: str, spec: Any, emitter: Any) -> Any:
        raise AssertionError("Approval workflow must not execute a sandbox node")


def _database_urls() -> tuple[str, str]:
    admin = os.environ["NEXUS_TEST_DATABASE_URL"]
    return admin, os.environ["NEXUS_TEST_APP_DATABASE_URL"]


def test_api_auth_workflow_approval_and_event_stream() -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL", "NEXUS_TEST_REDIS_URL")
    if any(key not in os.environ for key in required):
        pytest.skip("PostgreSQL and Redis integration services are not configured")

    async def check() -> None:
        os.environ["NEXUS_SECRET_KEY"] = "phase5-secret-key-for-tests-32-bytes-min"
        os.environ["NEXUS_API_KEY_PEPPER"] = "phase5-test-pepper-32-characters-minimum"
        tenant_id, workspace_id, admin_id, viewer_id, workflow_id = (uuid4() for _ in range(5))
        admin_url, app_url = _database_urls()
        root = Path(os.environ.get("NEXUS_SANDBOX_TEST_ROOT", "/tmp/nexus-phase5-api-test"))
        owner_engine = create_async_engine(admin_url)
        runtime_engine = create_async_engine(app_url)
        redis = Redis.from_url(os.environ["NEXUS_TEST_REDIS_URL"], decode_responses=True)
        qdrant = AsyncQdrantClient(url=os.environ.get("NEXUS_TEST_QDRANT_URL", "http://127.0.0.1:6333"), check_compatibility=False)
        dispatcher = InlineDispatcher()
        sandbox = ComputerSandboxSupervisor(runtime_engine, DockerSandboxProvider(root))
        services = AppServices(
            runtime_engine, redis, qdrant, sandbox,
            cast(AutoGenSandboxRunner, NoopSandboxRunner()), dispatcher,
        )
        dispatcher.services = services
        app = create_app(services)
        async with owner_engine.begin() as connection:
            await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'API Integration')"), {"id": tenant_id})
            await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :tenant, 'API Integration')"), {"id": workspace_id, "tenant": tenant_id})
            await connection.execute(text("INSERT INTO users (id, tenant_id, workspace_id, email, password_hash, display_name) VALUES (:admin, :tenant, :workspace, 'api-admin@example.invalid', :admin_hash, 'Admin'), (:viewer, :tenant, :workspace, 'api-viewer@example.invalid', :viewer_hash, 'Viewer')"), {
                "admin": admin_id, "viewer": viewer_id, "tenant": tenant_id, "workspace": workspace_id,
                "admin_hash": hash_password("a-long-admin-password"), "viewer_hash": hash_password("a-long-viewer-password"),
            })
            await connection.execute(text("INSERT INTO workspace_members (id, tenant_id, workspace_id, user_id, role) VALUES (:admin_member, :tenant, :workspace, :admin, 'admin'), (:viewer_member, :tenant, :workspace, :viewer, 'viewer')"), {"admin_member": uuid4(), "viewer_member": uuid4(), "tenant": tenant_id, "workspace": workspace_id, "admin": admin_id, "viewer": viewer_id})

        try:
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://nexus.test") as client:
                    login = await client.post("/api/v1/auth/token", json={
                        "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                        "email": "api-admin@example.invalid", "password": "a-long-admin-password",
                    })
                    assert login.status_code == 200, login.text
                    admin_token = login.json()["access_token"]
                    admin_headers = {"Authorization": f"Bearer {admin_token}"}
                    assert (await client.get("/api/v1/workflows", headers=admin_headers)).status_code == 200
                    assert (await client.get("/api/v1/workflows", headers={"Authorization": "Bearer invalid"})).status_code == 401
                    catalog = await client.get("/api/v1/templates")
                    assert catalog.status_code == 200 and len(catalog.json()) == 4
                    instantiated = await client.post(
                        "/api/v1/templates/executive-inbox-operations/instantiate",
                        json={}, headers=admin_headers,
                    )
                    assert instantiated.status_code == 201, instantiated.text
                    seeded = instantiated.json()
                    assert seeded["workflow_id"] and seeded["knowledge_base_id"] and seeded["bot_id"]
                    assert len(seeded["routine_ids"]) == 1
                    assert seeded["workflow"]["tenant_id"] == str(tenant_id)
                    async with scoped_session(runtime_engine, tenant_id, workspace_id) as session:
                        assert await session.get(Workflow, UUID(seeded["workflow_id"])) is not None
                        assert await session.get(KnowledgeBase, UUID(seeded["knowledge_base_id"])) is not None
                        assert await session.get(PersistentBot, UUID(seeded["bot_id"])) is not None
                        routine = await session.get(BotRoutine, UUID(seeded["routine_ids"][0]))
                        assert routine is not None and routine.workflow_id == UUID(seeded["workflow_id"])

                    viewer_login = await client.post("/api/v1/auth/token", json={
                        "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                        "email": "api-viewer@example.invalid", "password": "a-long-viewer-password",
                    })
                    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
                    spec = {
                        "id": str(workflow_id), "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                        "name": "Approval workflow", "version": 1,
                        "nodes": [
                            {"id": "start", "kind": "start", "trigger_type": "webhook", "input_schema": {"type": "object", "properties": {"request": {"type": "string"}}}},
                            {"id": "approve", "kind": "approval", "label": "Approval", "action_description": "Publish the result", "required_role": "admin"},
                        ],
                        "edges": [{"source": "start", "target": "approve"}],
                    }
                    denied_create = await client.post("/api/v1/workflows", json=spec, headers=viewer_headers)
                    assert denied_create.status_code == 403
                    created = await client.post("/api/v1/workflows", json=spec, headers=admin_headers)
                    assert created.status_code == 201, created.text
                    exported = await client.get(f"/api/v1/workflows/{workflow_id}/export?file_format=yaml", headers=admin_headers)
                    assert exported.status_code == 200 and "Approval workflow" in exported.text

                    key_response = await client.post("/api/v1/auth/keys", json={"scopes": ["read", "write", "run", "approve"]}, headers=admin_headers)
                    assert key_response.status_code == 201, key_response.text
                    key = key_response.json()["key"]
                    key_headers = {
                        "X-Nexus-API-Key": key,
                        "X-Nexus-Tenant-ID": str(tenant_id),
                        "X-Nexus-Workspace-ID": str(workspace_id),
                    }
                    assert (await client.get("/api/v1/workflows", headers=key_headers)).status_code == 200
                    assert (await client.get("/api/v1/workflows", headers={**key_headers, "X-Nexus-Workspace-ID": str(uuid4())})).status_code == 401

                    started = await client.post(f"/api/v1/workflows/{workflow_id}/runs", json={"input_data": {"task": "check"}}, headers=admin_headers)
                    assert started.status_code == 202, started.text
                    run_id = UUID(started.json()["run_id"])
                    state = await client.get(f"/api/v1/runs/{run_id}", headers=admin_headers)
                    assert state.json()["status"] == "paused"
                    async with scoped_session(runtime_engine, tenant_id, workspace_id) as session:
                        approval = await session.scalar(select(ApprovalRequest).where(ApprovalRequest.run_id == run_id))
                        assert approval is not None and approval.status == "pending"
                        approval_id = approval.id

                    async with httpx.AsyncClient(timeout=15) as network_client:
                        listener = socket.socket()
                        listener.bind(("127.0.0.1", 0))
                        listener.listen()
                        port = listener.getsockname()[1]
                        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
                        server_task = asyncio.create_task(server.serve(sockets=[listener]))
                        try:
                            for _ in range(100):
                                if server.started:
                                    break
                                await asyncio.sleep(0.05)
                            assert server.started
                            async with network_client.stream("GET", f"http://127.0.0.1:{port}/api/v1/runs/{run_id}/stream", headers=admin_headers) as response:
                                assert response.status_code == 200
                                await asyncio.sleep(0.2)
                                await RuntimeEventEmitter(redis, tenant_id, workspace_id, run_id).emit(RuntimeEventType.RUN_COMPLETED, {"source": "integration-test"})
                                received = ""
                                async for chunk in response.aiter_text():
                                    received += chunk
                                assert "event: RUN_COMPLETED" in received
                                assert str(run_id) in received
                        finally:
                            server.should_exit = True
                            await asyncio.wait_for(server_task, timeout=5)
                            listener.close()

                    resolved = await client.post(f"/api/v1/approvals/{approval_id}/resolve", json={"decision": "allow_once"}, headers=admin_headers)
                    assert resolved.status_code == 200, resolved.text
                    assert resolved.json()["status"] == "completed"
                    final = await client.get(f"/api/v1/runs/{run_id}", headers=admin_headers)
                    assert final.json()["status"] == "completed"
                    assert final.json()["node_outputs"]["start"] == {"task": "check"}
                    usage = await client.get(f"/api/v1/analytics/usage?days=365&workflow_id={workflow_id}&run_id={run_id}", headers=admin_headers)
                    assert usage.status_code == 200 and usage.json()["totals"]["prompt_tokens"] == 0
                    async with scoped_session(runtime_engine, tenant_id, workspace_id) as session:
                        resolved_row = await session.get(ApprovalRequest, approval_id)
                        audit = await session.scalar(select(AuditLog).where(AuditLog.target_id == approval_id, AuditLog.action == "approval.resolved"))
                        assert resolved_row is not None and resolved_row.status == "allowed_once"
                        assert audit is not None and audit.actor_id == admin_id
        finally:
            await redis.aclose()
            await qdrant.close()
            await runtime_engine.dispose()
            await owner_engine.dispose()

    asyncio.run(check())


def test_celery_dispatcher_enqueues_to_redis() -> None:
    if not os.environ.get("NEXUS_REDIS_PASSWORD") and not os.environ.get("NEXUS_REDIS_URL"):
        pytest.skip("Task queue Redis connection is not configured")

    async def check() -> None:
        dispatcher = CeleryDispatcher()
        await dispatcher.startup()
        try:
            await dispatcher.workflow(uuid4(), uuid4(), uuid4())
            await dispatcher.bot_turn(uuid4(), uuid4(), uuid4(), uuid4(), "test")
            await dispatcher.routine(uuid4(), uuid4(), uuid4())
        finally:
            await dispatcher.shutdown()

    asyncio.run(check())


def test_a_workflow_can_be_started_through_either_spelling_of_the_run_route() -> None:
    from fastapi.routing import APIRoute

    posts = {route.path for route in create_app(None).routes if isinstance(route, APIRoute) and "POST" in route.methods}
    assert {"/api/v1/workflows/{workflow_id}/run", "/api/v1/workflows/{workflow_id}/runs"} <= posts


def test_cors_allows_credentialed_requests_from_localhost_only_in_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    def preflight(origin: str) -> dict[str, str]:
        response = TestClient(create_app(None)).options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        allowed = response.headers.get("access-control-allow-origin")
        return {} if allowed is None else {"access-control-allow-origin": allowed, "access-control-allow-credentials": response.headers.get("access-control-allow-credentials", "")}

    monkeypatch.delenv("NEXUS_CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.setenv("NEXUS_CORS_ORIGINS", "https://studio.example.com")
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "false")
    assert preflight("https://studio.example.com") == {"access-control-allow-origin": "https://studio.example.com", "access-control-allow-credentials": "true"}
    assert preflight("http://localhost:4000") == {}, "a shared deployment does not accept arbitrary localhost origins"
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "true")
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000", "http://127.0.0.1:51789", "http://localhost"):
        assert preflight(origin) == {"access-control-allow-origin": origin, "access-control-allow-credentials": "true"}, origin
    for origin in ("https://evil.example", "http://localhost.evil.example", "http://127.0.0.1:3000.evil.example", "https://localhost:3000"):
        assert preflight(origin) == {}, origin
