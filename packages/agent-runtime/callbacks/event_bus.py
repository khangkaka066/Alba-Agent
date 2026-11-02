"""Publish validated runtime events on a run-specific Redis channel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis

from nexus_core_schema.models import RuntimeEvent, RuntimeEventType
from nexus_core_schema.artifacts import list_artifacts


class RuntimeEventEmitter:
    def __init__(self, redis: Redis, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        self._redis = redis
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.run_id = run_id
        self.channel = f"run:{tenant_id}:{run_id}:events"

    async def publish(self, event: RuntimeEvent) -> None:
        if (event.tenant_id, event.workspace_id, event.run_id) != (
            self.tenant_id, self.workspace_id, self.run_id
        ):
            raise ValueError("Runtime event scope does not match emitter scope")
        await self._redis.publish(self.channel, event.model_dump_json())

    async def emit(
        self, event_type: RuntimeEventType, payload: dict[str, Any], node_id: str | None = None
    ) -> RuntimeEvent:
        if event_type == RuntimeEventType.RUN_COMPLETED:
            payload = {**payload, "artifacts": list_artifacts(
                self.tenant_id, self.workspace_id, self.run_id, payload.get("node_outputs")
            )}
        event = RuntimeEvent(
            id=uuid4(),
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            node_id=node_id,
            type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
        await self.publish(event)
        return event
