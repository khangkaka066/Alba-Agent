#!/usr/bin/env python3
"""Exercise the running Compose stack from bootstrap through a resumed workflow.

Run from the repository root with ``python3 scripts/smoke_test.py``. The host
entrypoint starts the stack, then runs the database/API checks inside the API
container so it can use the configured private service network.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]


def _setting(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                return value.strip().strip("\"'")
    return default


API_URL = f"http://127.0.0.1:{_setting('NEXUS_API_PORT', '8000')}"


def _compose(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *arguments], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def _wait_for_api() -> None:
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{API_URL}/ready", timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    raise RuntimeError("Compose API did not become ready within 240 seconds")


def _host_main() -> int:
    try:
        build = _compose("up", "-d", "--build", "postgres", "redis", "qdrant", "sandbox-supervisor", "api", "worker", "web")
        if build.returncode:
            print("Could not build/start the Compose stack (docker compose returned a non-zero exit code).", file=sys.stderr)
            return build.returncode
        _wait_for_api()
        inside = _compose("exec", "-T", "api", "python", "/workspace/scripts/smoke_test.py", "--inside")
        if inside.stdout:
            print(inside.stdout, end="")
        if inside.returncode:
            if inside.stderr:
                print(inside.stderr.strip().splitlines()[-1], file=sys.stderr)
            print("Full-stack smoke test failed inside the API container.", file=sys.stderr)
            return inside.returncode
        print("Full-stack smoke test passed.")
        return 0
    except Exception as error:
        print(f"Full-stack smoke test failed: {error}", file=sys.stderr)
        return 1
    finally:
        down = _compose("down")
        if down.returncode:
            print("Warning: docker compose down did not complete successfully.", file=sys.stderr)


async def _inside_main() -> None:
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.auth.context import hash_password
    from app.models import AuditLog, Tenant, TenantBudget, User, Workspace, WorkspaceMember

    chat_model = os.environ.get("NEXUS_SMOKE_CHAT_MODEL", "openai/gpt-4.1-mini")
    auto_model = os.environ.get("NEXUS_SMOKE_AUTOGEN_MODEL", "gpt-4.1-mini")
    embedding_model = os.environ.get("NEXUS_SMOKE_EMBEDDING_MODEL", "openai/text-embedding-3-small")
    auto_qualified_model = auto_model if "/" in auto_model else f"openai/{auto_model}"
    required_models = (chat_model, embedding_model, auto_qualified_model)  # prices are optional: unpriced models run as SUBSCRIPTION_INCLUDED
    credentials_by_provider = {
        "openai": "NEXUS_OPENAI_API_KEY", "anthropic": "NEXUS_ANTHROPIC_API_KEY",
        "gemini": "NEXUS_GEMINI_API_KEY", "deepseek": "NEXUS_DEEPSEEK_API_KEY",
        "openrouter": "NEXUS_OPENROUTER_API_KEY",
    }
    missing_credentials = sorted({
        credentials_by_provider[model.partition("/")[0]]
        for model in required_models
        if model.partition("/")[0] in credentials_by_provider
        and not os.environ.get(credentials_by_provider[model.partition("/")[0]])
    })
    if not (os.environ.get("NEXUS_AUTOGEN_API_KEY") or os.environ.get("NEXUS_OPENAI_API_KEY")):
        missing_credentials.append("NEXUS_AUTOGEN_API_KEY or NEXUS_OPENAI_API_KEY")
    if missing_credentials:
        raise RuntimeError(
            f"A live AI workflow cannot run until provider credentials exist: {', '.join(missing_credentials)}. "
            "No credential values were printed."
        )

    setup_url = os.environ.get("NEXUS_SETUP_DATABASE_URL")
    if not setup_url:
        raise RuntimeError("NEXUS_SETUP_DATABASE_URL is not configured in the API service")
    tenant_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
    email = f"smoke-{user_id.hex}@example.invalid"
    password = "Nexus-Smoke-Test-Password-2026"
    admin_engine = create_async_engine(setup_url, pool_pre_ping=True)
    try:
        async with AsyncSession(admin_engine, expire_on_commit=False) as session:
            async with session.begin():
                session.add(Tenant(id=tenant_id, name="Nexus smoke tenant"))
                await session.flush()
                session.add(Workspace(id=workspace_id, tenant_id=tenant_id, name="Smoke workspace"))
                await session.flush()
                session.add(User(
                    id=user_id, tenant_id=tenant_id, workspace_id=workspace_id,
                    email=email, password_hash=hash_password(password), display_name="Smoke Owner",
                ))
                session.add(WorkspaceMember(
                    tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id, role="owner",
                ))
                session.add(TenantBudget(tenant_id=tenant_id, remaining_usd=100, reserved_usd=0, overage_usd=0))
    finally:
        await admin_engine.dispose()

    headers: dict[str, str] = {}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30) as client:
        login = await client.post("/api/v1/auth/token", json={
            "tenant_id": str(tenant_id), "workspace_id": str(workspace_id), "email": email, "password": password,
        })
        assert login.status_code == 200, login.text
        headers["authorization"] = f"Bearer {login.json()['access_token']}"

        knowledge = await client.post("/api/v1/knowledge-bases", headers=headers, json={
            "name": "Smoke documents", "embedding_model": embedding_model,
        })
        assert knowledge.status_code == 201, knowledge.text
        knowledge_id = knowledge.json()["id"]
        uploaded = await client.post(
            f"/api/v1/knowledge-bases/{knowledge_id}/documents?filename=smoke.csv",
            headers={**headers, "content-type": "text/csv"},
            content=b"topic,value\nsmoke marker,nexus-qdrant-smoke-unique-7319\n",
        )
        assert uploaded.status_code == 201, uploaded.text
        retrieved = await client.post(
            f"/api/v1/knowledge-bases/{knowledge_id}/query", headers=headers,
            json={"query": "nexus-qdrant-smoke-unique-7319", "limit": 5},
        )
        assert retrieved.status_code == 200 and any(
            "nexus-qdrant-smoke-unique-7319" in item["text"] for item in retrieved.json()
        ), retrieved.text

        workflow_id = str(uuid4())
        workflow = {
            "id": workflow_id, "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
            "name": f"Smoke workflow {workflow_id[:8]}", "version": 1,
            "nodes": [
                {"id": "trigger", "kind": "start", "trigger_type": "manual"},
                {"id": "research", "kind": "crew", "label": "Researcher", "agents": [{
                    "id": "researcher", "role": "Researcher", "goal": "Summarize the supplied task and knowledge context.",
                    "backstory": "A careful research analyst.", "model": chat_model,
                }], "tasks": [{
                    "id": "research_summary", "agent_id": "researcher",
                    "description": "Summarize the request in one concise result. Request: {input}",
                    "expected_output": "A concise result string in the required structured format.",
                    "output_schema": "NexusTextResult",
                }]},
                {"id": "coder", "kind": "sandbox", "label": "Python verification", "coder_model": auto_model,
                    "reviewer_model": auto_model, "sandbox_provider": "docker",
                    "coder_instructions": "Use Python to verify the requested CSV arithmetic.",
                    "reviewer_instructions": "Approve only after execution succeeds.",
                    "max_rounds": 4, "timeout_seconds": 120,
                    "verification_command": "python -c \"assert open('smoke-result.txt').read().strip() == '6'; print('verification passed')\""},
                {"id": "approval", "kind": "approval", "label": "Review result",
                    "action_description": "Approve the verified smoke-test result", "required_role": "owner"},
            ],
            "edges": [
                {"source": "trigger", "target": "research"},
                {"source": "research", "target": "coder"},
                {"source": "coder", "target": "approval"},
            ],
        }
        created = await client.post("/api/v1/workflows", headers=headers, json=workflow)
        assert created.status_code == 201, created.text
        run_response = await client.post(
            f"/api/v1/workflows/{workflow_id}/runs", headers=headers,
            json={"input_data": {"task": "Sum 1, 2, and 3, write the answer 6 to smoke-result.txt, and verify it."}},
        )
        assert run_response.status_code == 202, run_response.text
        run_id = run_response.json()["run_id"]
        events: list[dict[str, object]] = []

        async def consume_events() -> None:
            async with client.stream("GET", f"/api/v1/runs/{run_id}/stream", headers=headers, timeout=None) as response:
                assert response.status_code == 200
                current_data: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        current_data.append(line[5:].strip())
                    elif not line and current_data:
                        events.append(json.loads("\n".join(current_data)))
                        current_data.clear()
                        if events[-1].get("type") in ("RUN_COMPLETED", "RUN_FAILED"):
                            return

        event_task = asyncio.create_task(consume_events())
        approval_id: str | None = None
        deadline = time.monotonic() + 900
        try:
            while time.monotonic() < deadline:
                current = await client.get(f"/api/v1/runs/{run_id}", headers=headers)
                assert current.status_code == 200, current.text
                status = current.json()["status"]
                if status == "paused":
                    approval_id = current.json().get("pending_approval_id")
                    if approval_id:
                        break
                if status == "failed":
                    raise RuntimeError("Workflow worker marked the live smoke run failed")
                await asyncio.sleep(2)
            assert approval_id, "Workflow did not pause at its configured approval gate"
            resolution = await client.post(
                f"/api/v1/approvals/{approval_id}/resolve", headers=headers,
                json={"decision": "allow_once"}, timeout=900,
            )
            assert resolution.status_code == 200, resolution.text
            final_deadline = time.monotonic() + 180
            while time.monotonic() < final_deadline:
                current = await client.get(f"/api/v1/runs/{run_id}", headers=headers)
                if current.json()["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(1)
            assert current.json()["status"] == "completed", current.text
            usage = await client.get(
                f"/api/v1/analytics/usage?days=365&workflow_id={workflow_id}&run_id={run_id}", headers=headers,
            )
            assert usage.status_code == 200, usage.text
            totals = usage.json()["totals"]
            assert totals["prompt_tokens"] + totals["completion_tokens"] > 0, totals
            await asyncio.wait_for(event_task, timeout=20)
            event_types = {str(event.get("type")) for event in events}
            assert {"APPROVAL_REQUIRED", "SANDBOX_TERMINAL_OUTPUT", "RUN_COMPLETED"} <= event_types, event_types
            audit_engine = create_async_engine(setup_url, pool_pre_ping=True)
            try:
                async with audit_engine.connect() as connection:
                    audit_id = await connection.scalar(select(AuditLog.id).where(
                        AuditLog.tenant_id == tenant_id,
                        AuditLog.workspace_id == workspace_id,
                        AuditLog.target_id == UUID(approval_id),
                        AuditLog.action == "approval.resolved",
                    ).limit(1))
                assert audit_id is not None, "Approval resolution was not written to the audit log"
            finally:
                await audit_engine.dispose()
            print(json.dumps({
                "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                "knowledge_base_id": knowledge_id, "workflow_id": workflow_id, "run_id": run_id,
                "approval_resolved": True, "events": sorted(event_types), "usage": totals,
            }, indent=2))
        finally:
            if not event_task.done():
                event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)


if __name__ == "__main__":
    if "--inside" in sys.argv:
        asyncio.run(_inside_main())
    else:
        raise SystemExit(_host_main())
