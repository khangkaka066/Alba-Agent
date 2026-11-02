"""Tools available to a run: the per-run built-in registry and tools mounted for a whole workspace."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from nexus_builtin_tools import BuiltinToolRegistry

RUN_REGISTRY_LIMIT = 500


class ToolRegistryService:
    def __init__(self, run_limit: int = RUN_REGISTRY_LIMIT) -> None:
        self._run_limit = run_limit
        self.workspace_tools: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        self.run_registries: dict[tuple[UUID, UUID, UUID], BuiltinToolRegistry] = {}

    def mount_workspace_tool(self, tenant_id: UUID, workspace_id: UUID, tool_id: str, tool: Any) -> Callable[[], None]:
        """Make `tool` available to every run in one workspace; the returned callable removes it again, no restart needed."""
        tools = self.workspace_tools.setdefault((tenant_id, workspace_id), {})
        if tool_id in tools:
            raise ValueError(f"Tool '{tool_id}' is already mounted in this workspace")
        tools[tool_id] = tool

        def unmount() -> None:
            mounted = self.workspace_tools.get((tenant_id, workspace_id))
            if mounted is not None and mounted.get(tool_id) is tool:
                del mounted[tool_id]
                if not mounted:
                    del self.workspace_tools[(tenant_id, workspace_id)]

        return unmount

    def remember_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, registry: BuiltinToolRegistry) -> None:
        self.run_registries[(tenant_id, workspace_id, run_id)] = registry
        while len(self.run_registries) > self._run_limit:
            self.run_registries.pop(next(iter(self.run_registries)))

    def run_registry(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> BuiltinToolRegistry:
        registry = self.run_registries.get((tenant_id, workspace_id, run_id))
        if registry is None:
            raise LookupError("Run-scoped built-in tool registry is not available")
        return registry

    def autogen_tools(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, tool_ids: tuple[str, ...]) -> list[Any]:
        return self.run_registry(tenant_id, workspace_id, run_id).autogen_tools(tool_ids)

    def clear(self) -> None:
        self.workspace_tools.clear()
        self.run_registries.clear()
