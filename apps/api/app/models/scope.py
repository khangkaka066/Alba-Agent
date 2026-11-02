"""Transaction-local RLS scope for authenticated application requests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@asynccontextmanager
async def scoped_session(
    engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Bind trusted, already-authorized scope to one transaction.

    The engine must connect as a non-owner role without BYPASSRLS. Authentication
    and membership checks must happen before calling this function.
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('nexus.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('nexus.workspace_id', :workspace_id, true)"),
                {"workspace_id": str(workspace_id)},
            )
            yield session
