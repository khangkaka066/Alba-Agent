#!/usr/bin/env python3
"""Run an authorized real museum media workflow against the local Compose API."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.context import TenantContext, issue_access_token


PROMPT = (
    "Produce a playable 16:9 MP4 of a fixed security camera looking across a museum gallery. "
    "Visible artifacts stand in glass display cases while visitors walk naturally through the room. "
    "The viewpoint stays locked off with realistic surveillance framing and no camera movement."
)


async def main() -> None:
    setup_url = os.environ.get("NEXUS_SETUP_DATABASE_URL")
    if not setup_url:
        raise RuntimeError("Run this script inside the API container with its configured database URL")
    engine = create_async_engine(setup_url)
    try:
        async with engine.connect() as connection:
            account = (await connection.execute(text("""
                SELECT u.tenant_id, u.workspace_id, u.id, m.role
                FROM users u
                JOIN workspace_members m ON m.user_id = u.id AND m.workspace_id = u.workspace_id
                JOIN model_credentials c ON c.tenant_id = u.tenant_id AND c.workspace_id = u.workspace_id
                WHERE c.preset_id = 'shopaikey' AND c.status = 'connected' AND m.role IN ('owner', 'admin')
                ORDER BY u.created_at LIMIT 1
            """))).first()
        if account is None:
            raise RuntimeError("No owner/admin workspace has a connected ShopAIKey credential")
        tenant_id, workspace_id, user_id, role = account
    finally:
        await engine.dispose()
    headers = {"authorization": f"Bearer {issue_access_token(TenantContext(tenant_id, workspace_id, user_id, role))}"}
    workflow_id = uuid4()
    script_schema = {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}
    file_schema = {"type": "object", "properties": {"artifact_filename": {"type": "string"}, "report_filename": {"type": "string"}, "summary": {"type": "string"}}, "required": ["artifact_filename", "report_filename", "summary"]}
    spec = {
        "id": str(workflow_id), "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
        "name": f"Phase 16 Museum Camera Video {workflow_id.hex[:8]}", "version": 1,
        "nodes": [
            {"id": "start", "kind": "start", "label": "Museum request", "input_schema": {"type": "object"}},
            {"id": "production", "kind": "crew", "label": "Produce museum footage", "process": "sequential",
             "agents": [
                 {"id": "scriptwriter", "role": "Museum camera director", "goal": "Define one concise fixed security camera scene", "backstory": "Writes realistic camera briefs.", "model": "openai/gpt-4.1-mini", "tool_ids": [], "skill_ids": []},
                 {"id": "producer", "role": "Video production operator", "goal": "Call media tools and deliver an actual MP4 and report", "backstory": "Executes and verifies file-producing tools.", "model": "openai/gpt-4.1-mini", "tool_ids": ["media_generation", "report_exporter"], "skill_ids": []},
             ],
             "tasks": [
                 {"id": "script", "agent_id": "scriptwriter", "description": "Write a concise Veo prompt for fixed museum surveillance footage with display artifacts and visitors walking. The camera must not move.", "expected_output": "A complete production prompt", "output_schema": "MuseumScript", "output_schema_json": script_schema},
                 {"id": "produce", "agent_id": "producer", "context_task_ids": ["script"],
                  "description": "Execute media_generation with kind=video, model=veo3.1-fast, filename=museum_phase16 and the script prompt. Wait for the real MP4 tool result. Then execute report_exporter with format=markdown, filename=museum_phase16_script and the script plus production notes. Return the exact artifact filenames from those tool results; never invent a file.",
                  "expected_output": "Real MP4 and Markdown report filenames", "output_schema": "MuseumFiles", "output_schema_json": file_schema},
             ]},
            {"id": "approve_delivery", "kind": "approval", "label": "Approve final delivery", "action_description": "Review the produced museum video before final delivery", "required_role": "admin"},
            {"id": "delivery", "kind": "crew", "label": "Delivery handoff", "process": "sequential",
             "agents": [{"id": "delivery_agent", "role": "Delivery reviewer", "goal": "Confirm approved files are ready", "backstory": "Keeps a clear handoff record.", "model": "openai/gpt-4.1-mini", "tool_ids": [], "skill_ids": []}],
             "tasks": [{"id": "handoff", "agent_id": "delivery_agent", "description": "After approval, confirm the artifact filenames in the previous node output and return a concise delivery note. Do not call external publishing services.", "expected_output": "A concise approved handoff", "output_schema": "NexusTextResult"}]},
        ],
        "edges": [{"source": "start", "target": "production"}, {"source": "production", "target": "approve_delivery"}, {"source": "approve_delivery", "target": "delivery"}],
    }
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", headers=headers, timeout=45) as client:
        created = await client.post("/api/v1/workflows", json=spec)
        created.raise_for_status()
        queued = await client.post(f"/api/v1/workflows/{workflow_id}/runs", json={"input_data": {"task": PROMPT}})
        queued.raise_for_status()
        run_id = queued.json()["run_id"]
        print(f"workflow_id={workflow_id} run_id={run_id}", flush=True)
        approved = False
        for _attempt in range(180):
            await asyncio.sleep(5)
            state_response = await client.get(f"/api/v1/runs/{run_id}")
            state_response.raise_for_status()
            state = state_response.json()
            status = state["status"]
            if status == "paused" and not approved:
                approval_id = state.get("pending_approval_id")
                if not approval_id:
                    raise RuntimeError("Workflow paused without a visible approval ID")
                print(f"approval_before_delivery={approval_id}", flush=True)
                decision = await client.post(f"/api/v1/approvals/{approval_id}/resolve", json={"decision": "allow_once"})
                decision.raise_for_status()
                approved = True
            if status == "failed":
                raise RuntimeError(f"Workflow failed; node outputs: {state.get('node_outputs')}")
            if status == "completed":
                files = state.get("artifacts", [])
                if not approved or not any(item["filename"].endswith(".mp4") for item in files) or not any(item["filename"].endswith(".md") for item in files):
                    raise RuntimeError(f"Completed run lacks approval, MP4, or report: {files}")
                for item in files:
                    response = await client.get(item["download_url"])
                    response.raise_for_status()
                    if not response.content:
                        raise RuntimeError("Downloaded artifact is empty")
                    print(f"artifact={item['filename']} bytes={len(response.content)} status={response.status_code}", flush=True)
                print("museum_phase16_e2e=passed", flush=True)
                return
        raise TimeoutError("Museum workflow did not finish within fifteen minutes")


if __name__ == "__main__":
    asyncio.run(main())
