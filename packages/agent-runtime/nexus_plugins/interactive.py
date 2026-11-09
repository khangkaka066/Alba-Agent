"""Interactive terminal, snapshots, browser and preview capabilities on scoped computers."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from callbacks.event_bus import RuntimeEventEmitter
from nexus_computer_sandbox.interactive import InteractiveComputers
from nexus_computer_sandbox.supervisor import ComputerAccess
from nexus_core_schema.models import RuntimeEventType
from nexus_kernel import Context, Plugin
from nexus_plugins.seams import INTERACTIVE_COMPUTERS, REDIS, SANDBOX


class InteractiveComputerPlugin(Plugin):
    name = "sandbox.interactive"
    requires = (SANDBOX, REDIS)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        supervisor = ctx.service(SANDBOX)
        redis = ctx.service(REDIS)
        async def publish(access: ComputerAccess, kind: str, payload: dict[str, Any]) -> None:
            if access.run_id is not None:
                await RuntimeEventEmitter(redis, access.tenant_id, access.workspace_id, access.run_id).emit(RuntimeEventType(kind), payload)
        service = InteractiveComputers(supervisor, publish)
        supervisor._on_command = service.watch
        supervisor._on_retire = service.stop
        def remove() -> None:
            supervisor._on_command = None
            supervisor._on_retire = None
        ctx.on_dispose(remove)
        ctx.on_dispose(service.close)
        ctx.provide(INTERACTIVE_COMPUTERS, service)
