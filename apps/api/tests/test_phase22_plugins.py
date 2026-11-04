"""The runtime's own plugins: boundaries between them, the default plugin list, and disabling a capability."""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

import nexus_kernel
import nexus_plugins
from nexus_kernel import Context, Kernel, Plugin, PluginState, build_rows, dump_rows, parse_rows
from nexus_plugins import DEFAULT_PLUGINS, default_registry
from nexus_plugins.seams import DATABASE, LLM, QDRANT, REDIS, SANDBOX, SANDBOX_RUNNER, TOOLS

KERNEL_DIR = Path(nexus_kernel.__file__).parent
PLUGIN_DIR = Path(nexus_plugins.__file__).parent
PLUGIN_MODULES = sorted(path for path in PLUGIN_DIR.glob("*.py") if path.stem not in {"__init__", "__main__", "seams"})


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
            found.extend("." * node.level + (node.module or "") + "." + alias.name for alias in node.names if node.level)
    return found


def test_the_kernel_depends_on_nothing_but_the_standard_library_and_yaml() -> None:
    allowed = {"yaml", "__future__"}
    standard = {"asyncio", "functools", "inspect", "logging", "abc", "collections", "dataclasses", "enum", "typing", "pathlib"}
    for path in KERNEL_DIR.glob("*.py"):
        for name in _imports(path):
            if name.startswith("."):
                continue
            assert name.split(".")[0] in allowed | standard, f"{path.name} imports {name}: the kernel must stay free of business logic"


def test_no_plugin_imports_another_plugin_or_the_control_plane() -> None:
    names = {path.stem for path in PLUGIN_MODULES}
    assert {"infrastructure", "llm", "memory", "sandbox", "sandbox_runner", "tools"} <= names
    for path in PLUGIN_MODULES:
        for name in _imports(path):
            parts = name.lstrip(".").split(".")
            assert not (name.startswith(".") and parts[0] in names), f"{path.name} imports sibling plugin {name}"
            assert not (parts[0] == "nexus_plugins" and len(parts) > 1 and parts[1] in names), f"{path.name} imports plugin {name}"
            assert name != "app.services" and not name.startswith("app.routers"), f"{path.name} reaches into the control plane"


def test_every_plugin_class_declares_its_dependencies_through_seam_keys() -> None:
    registry = default_registry()
    for name in registry.names():
        plugin = registry.create(name)
        assert plugin.name == name
        assert all(hasattr(key, "name") for key in plugin.requires + plugin.optional)


def test_the_default_list_names_only_registered_plugins_and_round_trips() -> None:
    rows = build_rows(DEFAULT_PLUGINS)
    registry = default_registry()
    assert {row.plugin for row in rows} <= set(registry.names()) and len({row.id for row in rows}) == len(rows)
    assert {row.plugin for row in rows} == set(registry.names())  # nothing registered is left out of the default boot
    assert parse_rows(__import__("yaml").safe_load(dump_rows(rows))) == rows


class StandInInfrastructure(Plugin):
    """Provides lazy connections so the rest of the default list can start without Postgres, Redis or Qdrant."""

    name = "infrastructure.runtime"

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        ctx.provide(DATABASE, create_async_engine("postgresql+asyncpg://nobody:none@127.0.0.1:1/none"))
        ctx.provide(REDIS, Redis(host="127.0.0.1", port=1))
        ctx.provide(QDRANT, AsyncQdrantClient(url="http://127.0.0.1:1"))


def test_the_default_plugin_list_boots_and_a_capability_can_be_switched_off_and_on() -> None:
    async def check() -> None:
        registry = default_registry()
        registry._factories["infrastructure.runtime"] = StandInInfrastructure  # connections are stood in; every other plugin is the real one
        kernel = Kernel(registry)
        await kernel.boot(build_rows(DEFAULT_PLUGINS))
        root = kernel.root
        supervisor = root.service(SANDBOX)
        assert supervisor.provider_names() == ("docker",)
        assert root.has(LLM) and root.has(TOOLS) and root.has(SANDBOX_RUNNER)

        # A provider plugin removed: its capability disappears, the supervisor and everything else stay.
        await kernel.handles["sandbox-docker"].stop()
        assert supervisor.provider_names() == () and kernel.handles["sandbox-runner"].state is PluginState.ACTIVE
        await kernel.handles["sandbox-docker"].start()
        assert supervisor.provider_names() == ("docker",)

        # The tool registry removed: everything built on it stops and nothing it handed out lingers.
        tools = root.service(TOOLS)
        tenant, workspace = uuid4(), uuid4()
        unmount = tools.mount_workspace_tool(tenant, workspace, "extra", object())
        assert tools.workspace_tools[(tenant, workspace)]
        await kernel.handles["tools"].stop()
        assert not root.has(TOOLS) and not tools.workspace_tools
        assert kernel.handles["sandbox-runner"].state.value == "pending" and not root.has(SANDBOX_RUNNER)
        unmount()  # unmounting after the registry went away must be harmless
        await kernel.handles["tools"].start()
        assert root.has(TOOLS) and kernel.handles["sandbox-runner"].state is PluginState.ACTIVE and root.has(SANDBOX_RUNNER)

        # Removing the database stops everything that needs it, in dependency order, and restores it afterwards.
        await kernel.handles["infrastructure"].stop()
        assert {key for key, handle in kernel.handles.items() if handle.state is PluginState.ACTIVE} == {"tools"}
        await kernel.handles["infrastructure"].start()
        # The local sandbox is listed but off until a patch enables it, so it never starts on a machine without macOS sandboxing.
        assert all(handle.state is PluginState.ACTIVE for key, handle in kernel.handles.items() if key != "sandbox-local")
        assert kernel.handles["sandbox-local"].state is not PluginState.ACTIVE
        await kernel.close()
        assert not root._services

    asyncio.run(check())


def test_a_workspace_tool_can_be_mounted_and_unmounted_without_touching_other_workspaces() -> None:
    from nexus_plugins.support.tool_service import ToolRegistryService

    service = ToolRegistryService()
    tenant, first, second = uuid4(), uuid4(), uuid4()
    unmount_first = service.mount_workspace_tool(tenant, first, "search", object())
    service.mount_workspace_tool(tenant, second, "search", object())
    unmount_first()
    assert (tenant, first) not in service.workspace_tools and (tenant, second) in service.workspace_tools
    unmount_first()  # idempotent


def test_run_registries_are_bounded_and_missing_ones_are_reported() -> None:
    from nexus_plugins.support.tool_service import ToolRegistryService

    service = ToolRegistryService(run_limit=2)
    tenant, workspace = uuid4(), uuid4()
    runs = [uuid4() for _ in range(3)]
    for run in runs:
        service.remember_run(tenant, workspace, run, object())  # type: ignore[arg-type]
    assert list(service.run_registries) == [(tenant, workspace, runs[1]), (tenant, workspace, runs[2])]
    try:
        service.run_registry(tenant, workspace, runs[0])
    except LookupError:
        return
    raise AssertionError("an evicted registry must not be returned")


def test_services_built_by_the_kernel_close_through_it_and_hand_built_ones_close_their_connections() -> None:
    from typing import cast

    from app.services import AppServices

    class Closing:
        def __init__(self, log: list[str], name: str) -> None:
            self.log, self.name = log, name

        async def aclose(self) -> None:
            self.log.append(self.name)

        async def close(self) -> None:
            self.log.append(self.name)

        async def dispose(self) -> None:
            self.log.append(self.name)

    async def check() -> None:
        log: list[str] = []
        engine, redis, qdrant = Closing(log, "engine"), Closing(log, "redis"), Closing(log, "qdrant")
        by_hand = AppServices(cast(Any, engine), cast(Any, redis), cast(Any, qdrant), cast(Any, None), cast(Any, None), cast(Any, None))
        await by_hand.shutdown()
        assert sorted(log) == ["engine", "qdrant", "redis"]

        log.clear()
        kernel = Kernel(default_registry())
        closed: list[str] = []

        async def close() -> None:
            closed.append("kernel")

        kernel.close = close  # type: ignore[method-assign]
        through_kernel = AppServices(cast(Any, engine), cast(Any, redis), cast(Any, qdrant), cast(Any, None), cast(Any, None), cast(Any, None), kernel=kernel)
        await through_kernel.shutdown()
        assert closed == ["kernel"] and log == []  # the plugins own the connections, so nothing is closed twice

    asyncio.run(check())


def test_dump_config_prints_the_list_with_patches_applied(tmp_path: Path, capsys: Any) -> None:
    from nexus_plugins.__main__ import main

    patch = tmp_path / "patch.yaml"
    patch.write_text("plugins:\n  - id: sandbox-docker\n    disabled: true\n  - id: llm\n    config: {tier: lab}\n", encoding="utf-8")
    assert main(["dump-config", "--patch", str(patch)]) == 0
    rows = {row.id: row for row in parse_rows(__import__("yaml").safe_load(capsys.readouterr().out))}
    assert rows["sandbox-docker"].disabled is True and dict(rows["llm"].config) == {"tier": "lab"}
    assert main([]) == 2
