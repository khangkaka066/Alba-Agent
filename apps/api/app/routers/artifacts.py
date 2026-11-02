"""Find deliverables of earlier tasks in this workspace, so a new task can start from them."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.auth.context import TenantContext, require_role
from app.models import Workflow, WorkflowRun
from app.models.scope import scoped_session
from app.routers.common import get_services
from nexus_core_schema.artifacts import list_artifacts

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
RUNS_SCANNED = 40


@router.get("/search")
async def search_artifacts(request: Request, context: READ, q: Annotated[str, Query(max_length=120)] = "", limit: Annotated[int, Query(ge=1, le=60)] = 30) -> list[dict[str, Any]]:
    """Files from the newest tasks, matching `q` against the file name or the task name. Only this workspace's runs are visible."""
    needle = q.strip().lower()
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        runs = (await session.scalars(select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(RUNS_SCANNED))).all()
        names = {row.id: row.name for row in (await session.scalars(select(Workflow).where(Workflow.id.in_({run.workflow_id for run in runs})))).all()} if runs else {}
    found: list[dict[str, Any]] = []
    for run in runs:
        task = names.get(run.workflow_id, "")
        for item in list_artifacts(context.tenant_id, context.workspace_id, run.id):
            if needle and needle not in item["filename"].lower() and needle not in task.lower():
                continue
            found.append({"run_id": str(run.id), "run_name": task, "run_status": run.status, "filename": item["filename"], "mime_type": item["mime_type"],
                          "size_bytes": item["size_bytes"], "created_at": run.created_at})
            if len(found) >= limit:
                return found
    return found
