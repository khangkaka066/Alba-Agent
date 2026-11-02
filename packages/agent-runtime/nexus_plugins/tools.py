"""Tool seam: per-run built-in registries and tools mounted for a workspace."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nexus_kernel import Context, Plugin
from nexus_plugins.seams import TOOLS
from nexus_plugins.support.tool_service import ToolRegistryService


class ToolRegistryPlugin(Plugin):
    name = "tools.registry"

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        service = ToolRegistryService(int(config.get("run_limit", 500)))
        ctx.on_dispose(service.clear)  # nothing a stopped registry handed out may linger
        ctx.provide(TOOLS, service)
