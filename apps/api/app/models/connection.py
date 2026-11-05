"""Create a database engine using only the restricted runtime role."""

from __future__ import annotations

import os

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_runtime_engine() -> AsyncEngine:
    user = os.environ["NEXUS_DB_USER"]
    if user != "nexus_runtime":
        raise ValueError("Runtime database user must be nexus_runtime")
    url = URL.create(
        "postgresql+asyncpg",
        username=user,
        password=os.environ["NEXUS_DB_PASSWORD"],
        host=os.environ["NEXUS_DB_HOST"],
        port=int(os.environ.get("NEXUS_DB_PORT", "5432")),
        database=os.environ["NEXUS_DB_NAME"],
    )
    return create_async_engine(url, pool_pre_ping=True)
