"""Read and update execution preferences within the authenticated workspace."""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from app.auth.context import TenantContext, require_role
from app.execution_settings import ExecutionSettings, execution_key, load_execution_settings
from app.models import AuditLog
from app.models.scope import scoped_session
from app.routers.common import get_services

router = APIRouter(prefix="/api/v1/settings/execution", tags=["settings"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
ADMIN = Annotated[TenantContext, Depends(require_role("admin", "write"))]


@router.get("")
async def read_execution_settings(request: Request, context: READ) -> ExecutionSettings:
    return await load_execution_settings(get_services(request).redis, context.tenant_id, context.workspace_id)


@router.put("")
async def update_execution_settings(body: ExecutionSettings, request: Request, context: ADMIN) -> ExecutionSettings:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id,
                             action="settings.execution_updated", target_type="workspace", target_id=context.workspace_id,
                             details=body.model_dump()))
    await services.redis.set(execution_key(context.tenant_id, context.workspace_id), body.model_dump_json())
    return body
