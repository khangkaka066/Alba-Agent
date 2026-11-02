#!/usr/bin/env python3
"""Verify that a live Crew calls report_exporter and writes a real file."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.context import TenantContext, issue_access_token


async def main() -> None:
    engine = create_async_engine(os.environ["NEXUS_SETUP_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(text("""
                SELECT u.tenant_id, u.workspace_id, u.id, m.role FROM users u
                JOIN workspace_members m ON m.user_id = u.id AND m.workspace_id = u.workspace_id
                JOIN model_credentials c ON c.tenant_id = u.tenant_id AND c.workspace_id = u.workspace_id
                WHERE c.preset_id = 'shopaikey' AND c.status = 'connected'
                AND m.role IN ('owner', 'admin') LIMIT 1
            """))).first()
    finally:
        await engine.dispose()
    if row is None:
        raise RuntimeError("No connected owner workspace")
    tenant_id, workspace_id, user_id, role = row
    workflow_id = uuid4()
    stem = f"phase16_report_probe_{workflow_id.hex[:8]}"
    spec = {
        "id": str(workflow_id), "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
        "name": f"Phase16 tool execution probe {workflow_id.hex[:8]}", "version": 1,
        "nodes": [
            {"id": "start", "kind": "start", "label": "Start", "input_schema": {"type": "object"}},
            {"id": "write_report", "kind": "crew", "label": "Write actual file", "process": "sequential",
             "agents": [{"id": "writer", "role": "Report operator", "goal": "Call report_exporter to write a file",
                         "backstory": "Delivers real files and checks tool results.", "model": "openai/gpt-4.1-mini",
                         "tool_ids": ["report_exporter"], "skill_ids": []}],
             "tasks": [{"id": "write", "agent_id": "writer",
                        "description": f"Call report_exporter with content='Museum camera tool execution probe', filename='{stem}', format='markdown'. After the tool returns, give a short summary. A plan is insufficient.",
                        "expected_output": "A saved Markdown file and brief summary", "output_schema": "Phase16ToolProbe",
                        "output_schema_json": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}]},
        ],
        "edges": [{"source": "start", "target": "write_report"}],
    }
    token = issue_access_token(TenantContext(tenant_id, workspace_id, user_id, role))
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", headers={"authorization": f"Bearer {token}"}, timeout=30) as client:
        created = await client.post("/api/v1/workflows", json=spec)
        if created.status_code != 200 and created.status_code != 201:
            raise RuntimeError(f"Workflow creation failed: {created.status_code} {created.text[:1000]}")
        queued = await client.post(f"/api/v1/workflows/{workflow_id}/runs", json={"input_data": {"task": "Write the report file now"}})
        queued.raise_for_status()
        run_id = queued.json()["run_id"]
        for _ in range(36):
            await asyncio.sleep(5)
            response = await client.get(f"/api/v1/runs/{run_id}")
            response.raise_for_status()
            state = response.json()
            if state["status"] in {"completed", "failed"}:
                filenames = [item["filename"] for item in state["artifacts"]]
                print({"run_id": run_id, "status": state["status"], "files": filenames}, flush=True)
                if state["status"] != "completed" or f"{stem}.md" not in filenames:
                    raise RuntimeError("Crew did not create the report file")
                return
        raise TimeoutError("Crew tool probe did not finish")


if __name__ == "__main__":
    asyncio.run(main())
