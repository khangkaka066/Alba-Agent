"""Database, Redis and vector-store connections, opened when the plugin starts and closed when it stops."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.models.connection import create_runtime_engine
from nexus_kernel import Context, Plugin
from nexus_plugins.seams import DATABASE, QDRANT, REDIS


class InfrastructurePlugin(Plugin):
    name = "infrastructure.runtime"

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        engine = create_runtime_engine()
        ctx.on_dispose(engine.dispose)
        redis = Redis(
            host=str(config.get("redis_host") or os.environ.get("NEXUS_REDIS_HOST", "redis")),
            port=int(os.environ.get("NEXUS_REDIS_PORT", "6379")),
            password=os.environ["NEXUS_REDIS_PASSWORD"], decode_responses=True,
        )
        ctx.on_dispose(redis.aclose)
        qdrant = AsyncQdrantClient(url=str(config.get("qdrant_url") or os.environ.get("NEXUS_QDRANT_URL", "http://qdrant:6333")))
        ctx.on_dispose(qdrant.close)
        ctx.provide(DATABASE, engine)
        ctx.provide(REDIS, redis)
        ctx.provide(QDRANT, qdrant)
