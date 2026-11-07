"""The runtime's capabilities as plugins, plus the default plugin list the API and workers boot."""

from __future__ import annotations

import os
from pathlib import Path

from nexus_kernel import Kernel, PluginRegistry, PluginRow, build_rows

DEFAULT_PLUGINS = Path(__file__).with_name("default.yaml")


def default_registry() -> PluginRegistry:
    """Every plugin that configuration may name. Imports are local so reading this package stays cheap."""
    from .infrastructure import InfrastructurePlugin
    from .llm import GatewayLlmPlugin
    from .memory import CheckpointsPlugin
    from .sandbox import DockerSandboxPlugin, LocalSandboxPlugin, SandboxSupervisorPlugin
    from .sandbox_runner import SandboxRunnerPlugin
    from .tools import ToolRegistryPlugin

    registry = PluginRegistry()
    for plugin in (InfrastructurePlugin, GatewayLlmPlugin, CheckpointsPlugin, SandboxSupervisorPlugin, DockerSandboxPlugin, LocalSandboxPlugin, SandboxRunnerPlugin, ToolRegistryPlugin):
        registry.register(plugin.name, plugin)
    return registry


def default_rows() -> list[PluginRow]:
    """The default list, optionally replaced by `NEXUS_PLUGINS_FILE` and layered with `NEXUS_PLUGIN_PATCHES` (comma separated)."""
    base = Path(os.environ.get("NEXUS_PLUGINS_FILE") or DEFAULT_PLUGINS)
    patches = tuple(Path(item.strip()) for item in os.environ.get("NEXUS_PLUGIN_PATCHES", "").split(",") if item.strip())
    return build_rows(base, patches)


async def boot_default() -> Kernel:
    kernel = Kernel(default_registry())
    await kernel.boot(default_rows())
    return kernel
