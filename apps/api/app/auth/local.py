"""Single-user local mode: a ready-made owner workspace, so the app opens without any sign-in.

This hands a full owner session to whoever can reach the API, so it is off unless ``NEXUS_LOCAL_MODE=true``.
The local compose stack turns it on and binds the API and web ports to 127.0.0.1; the production stack never does.
"""

from __future__ import annotations

import os
import secrets
from decimal import Decimal
from typing import cast
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.context import Role, TenantContext, hash_password
from app.models import Tenant, TenantBudget, User, Workspace, WorkspaceMember

LOCAL_EMAIL = "local@nexus.local"
LOCAL_NAME = "Local Workspace"


def local_mode_enabled() -> bool:
    return os.environ.get("NEXUS_LOCAL_MODE", "false").lower() == "true"


async def ensure_local_workspace(database_url: str) -> TenantContext:
    """Return the local owner context, creating the tenant, workspace, owner and starting credit once."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(text("SELECT pg_advisory_xact_lock(741926382)"))
                user = await session.scalar(select(User).where(User.email == LOCAL_EMAIL).limit(1))
                if user is None:
                    tenant_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
                    # ENTERPRISE has no plan limits: the single local user is not a metered customer.
                    session.add(Tenant(id=tenant_id, name=LOCAL_NAME, plan="ENTERPRISE"))
                    await session.flush()
                    session.add(Workspace(id=workspace_id, tenant_id=tenant_id, name=LOCAL_NAME))
                    await session.flush()
                    # Nobody signs in with a password here; the hash only satisfies the schema.
                    session.add(User(id=user_id, tenant_id=tenant_id, workspace_id=workspace_id, email=LOCAL_EMAIL,
                                     password_hash=hash_password(secrets.token_urlsafe(32)), display_name="Local owner"))
                    session.add(WorkspaceMember(tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id, role="owner"))
                    session.add(TenantBudget(tenant_id=tenant_id, remaining_usd=Decimal(os.environ.get("NEXUS_NEW_TENANT_CREDIT_USD", "10")),
                                             reserved_usd=Decimal("0"), overage_usd=Decimal("0")))
                    return TenantContext(tenant_id, workspace_id, user_id, "owner")
                member = await session.scalar(select(WorkspaceMember).where(
                    WorkspaceMember.tenant_id == user.tenant_id, WorkspaceMember.workspace_id == user.workspace_id,
                    WorkspaceMember.user_id == user.id))
                return TenantContext(user.tenant_id, user.workspace_id, user.id, cast(Role, member.role if member else "owner"))
    finally:
        await engine.dispose()
