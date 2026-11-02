"""Plugin kernel: mounting, dependency-driven lifecycle, reversible registrations, events, configuration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from nexus_kernel import (
    BootError, ConfigError, Context, EventMode, EventModeError, Kernel, Plugin, PluginRegistry, PluginRow, PluginState, ServiceConflictError,
    ServiceKey, ServiceMissingError, apply_patch, dump_rows, parse_rows,
)

GREETER: ServiceKey[str] = ServiceKey("greeter")
PROMPTS: ServiceKey[list[str]] = ServiceKey("prompts")
TOOLS: ServiceKey[dict[str, str]] = ServiceKey("tools")


class Recorder:
    def __init__(self) -> None:
        self.log: list[str] = []


def _drop(items: list[str], item: str) -> None:
    items.remove(item)


def _forget(items: dict[str, str], key: str) -> None:
    items.pop(key, None)


class PromptHost(Plugin):
    name = "prompt-host"

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        ctx.provide(PROMPTS, [])
        ctx.provide(TOOLS, {})


class Contributor(Plugin):
    """Adds a system prompt section, a tool and an event listener, the three things that must vanish on removal."""

    name = "contributor"
    requires = (PROMPTS, TOOLS)

    def __init__(self, recorder: Recorder | None = None) -> None:
        self.recorder = recorder

    def _record(self, label: str) -> Callable[[], None]:
        def record() -> None:
            if self.recorder is not None:
                self.recorder.log.append(label)

        return record

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        prompts, tools = ctx.service(PROMPTS), ctx.service(TOOLS)
        label = str(config.get("label", "x"))
        prompts.append(f"section:{label}")
        ctx.on_dispose(lambda: _drop(prompts, f"section:{label}"))
        tools[label] = "tool"
        ctx.on_dispose(lambda: _forget(tools, label))
        ctx.on("ping", self._record(label))


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


def test_a_plugin_waits_for_its_service_then_starts_and_stops_with_it() -> None:
    async def check() -> None:
        root = Context()
        contributor = await root.mount(Contributor(), {"label": "a"})
        assert contributor.state.value == "pending" and contributor.missing() == ("prompts", "tools")
        host = await root.mount(PromptHost())
        assert (host.state.value, contributor.state.value) == ('active', 'active')
        assert root.service(PROMPTS) == ["section:a"] and root.service(TOOLS) == {"a": "tool"}
        await host.stop()
        assert contributor.state.value == "pending" and not root.has(PROMPTS)
        await host.start()
        assert contributor.state.value == "active" and root.service(PROMPTS) == ["section:a"]
        await root.dispose()

    run(check())


def test_removing_a_plugin_strips_its_prompts_tools_and_listeners() -> None:
    async def check() -> None:
        recorder, root = Recorder(), Context()
        root.declare_event("ping", EventMode.EMIT)
        await root.mount(PromptHost())
        first = await root.mount(Contributor(recorder), {"label": "one"}, id="one")
        await root.mount(Contributor(recorder), {"label": "two"}, id="two")
        root.emit("ping")
        assert recorder.log == ["one", "two"]
        await first.stop()
        recorder.log.clear()
        root.emit("ping")
        assert recorder.log == ["two"]
        assert root.service(PROMPTS) == ["section:two"] and root.service(TOOLS) == {"two": "tool"}
        await root.dispose()
        assert root._listeners.get("ping", []) == []

    run(check())


def test_a_failing_plugin_is_rolled_back_and_does_not_stop_the_others() -> None:
    class Broken(Plugin):
        name = "broken"

        async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
            ctx.provide(GREETER, "half-registered")
            ctx.on("ping", lambda: None)
            raise RuntimeError("cannot start")

    async def check() -> None:
        root = Context()
        await root.mount(PromptHost())
        broken = await root.mount(Broken())
        good = await root.mount(Contributor(), {"label": "ok"})
        assert broken.state is PluginState.FAILED and isinstance(broken.error, RuntimeError)
        assert not root.has(GREETER) and broken.scope is None
        assert [entry.owner.name for entry in root._listeners["ping"]] == ["plugin:contributor"]  # only the healthy plugin's listener remains
        assert good.state is PluginState.ACTIVE
        await root.dispose()

    run(check())


def test_a_service_cannot_be_provided_twice_in_one_scope_but_scopes_are_isolated() -> None:
    async def check() -> None:
        root = Context()
        root.provide(GREETER, "root")
        with pytest.raises(ServiceConflictError):
            root.provide(GREETER, "again")
        workspace_a, workspace_b = root.scope("a"), root.scope("b")
        workspace_a.provide(PROMPTS, ["only a"])
        assert workspace_a.service(GREETER) == "root" and workspace_a.service(PROMPTS) == ["only a"]
        assert not workspace_b.has(PROMPTS)
        with pytest.raises(ServiceMissingError):
            workspace_b.service(PROMPTS)
        await root.dispose()

    run(check())


def test_listeners_in_one_scope_do_not_hear_a_sibling_scope() -> None:
    async def check() -> None:
        root, heard = Context(), []
        a, b = root.scope("a"), root.scope("b")
        a.on("ping", lambda who: heard.append(f"a:{who}"))
        root.on("ping", lambda who: heard.append(f"root:{who}"))
        b.emit("ping", "from-b")
        a.emit("ping", "from-a")
        assert heard == ["root:from-b", "root:from-a", "a:from-a"]
        await root.dispose()

    run(check())


def test_disposal_runs_newest_first_and_survives_a_failing_disposer() -> None:
    async def check() -> None:
        order: list[str] = []
        root = Context()
        scope = root.scope("s")
        scope.on_dispose(lambda: order.append("first"))

        def explode() -> None:
            raise RuntimeError("boom")

        scope.on_dispose(explode)
        scope.on_dispose(lambda: order.append("last"))
        with pytest.raises(ExceptionGroup):
            await root.dispose()
        assert order == ["last", "first"]

    run(check())


def test_event_modes_each_behave_as_documented_and_declared_modes_are_enforced() -> None:
    async def check() -> None:
        root = Context()
        seen: list[str] = []

        async def slow(value: int) -> int:
            await asyncio.sleep(0)
            seen.append(f"slow{value}")
            return value + 1

        root.on("s", slow)
        root.on("s", lambda value: value * 10)
        assert await root.serial("s", 1) == [2, 10]

        root.on("b", lambda: None)
        root.on("b", lambda: "winner")
        root.on("b", lambda: "never")
        assert await root.bail("b") == "winner"

        async def wrap(request: list[str], nxt: Any) -> str:
            request.append("outer")
            return f"[{await nxt()}]"

        def inner(request: list[str], nxt: Any) -> Any:
            request.append("inner")
            return nxt()

        root.on("w", wrap)
        root.on("w", inner)
        trail: list[str] = []
        assert await root.waterfall("w", trail, terminal=lambda request: "core") == "[core]" and trail == ["outer", "inner"]

        root.on("block", lambda request, nxt: "denied")
        assert await root.waterfall("block", [], terminal=lambda request: "executed") == "denied"

        replaced: list[Any] = []

        def land(value: int) -> int:
            replaced.append(value)
            return value

        root.on("swap", lambda value, nxt: nxt(value + 1))
        assert await root.waterfall("swap", 1, terminal=land) == 2

        root.declare_event("fixed", EventMode.SERIAL)
        with pytest.raises(EventModeError):
            root.emit("fixed")
        with pytest.raises(EventModeError):
            root.declare_event("fixed", EventMode.EMIT)

        root.on("p", lambda: seen.append("p1"))

        async def failing() -> None:
            raise ValueError("x")

        root.on("p", failing)
        with pytest.raises(ExceptionGroup):
            await root.parallel("p")
        await root.dispose()

    run(check())


def test_async_emit_listeners_are_cancelled_on_shutdown() -> None:
    async def check() -> None:
        root, started = Context(), asyncio.Event()

        async def forever() -> None:
            started.set()
            await asyncio.sleep(3600)

        root.on("go", forever)
        root.emit("go")
        await started.wait()
        assert len(root._shared.tasks) == 1
        await root.dispose()
        assert not root._shared.tasks

    run(check())


def test_an_optional_service_appearing_restarts_the_plugin_that_uses_it() -> None:
    class Adaptive(Plugin):
        name = "adaptive"
        optional = (GREETER,)

        def __init__(self, seen: list[str | None]) -> None:
            self.seen = seen

        async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
            self.seen.append(ctx.maybe(GREETER))

    class Greeter(Plugin):
        name = "greeter"

        async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
            ctx.provide(GREETER, "hello")

    async def check() -> None:
        seen: list[str | None] = []
        root = Context()
        await root.mount(Adaptive(seen))
        greeter = await root.mount(Greeter())
        await greeter.stop()
        assert seen == [None, "hello", None]
        await root.dispose()

    run(check())


def test_reload_restarts_dependents_around_the_changed_plugin() -> None:
    class Counted(Plugin):
        name = "counted"

        def __init__(self, starts: list[str]) -> None:
            self.starts = starts

        async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
            self.starts.append(str(config.get("v")))
            ctx.provide(GREETER, str(config.get("v")))

    class Consumer(Plugin):
        name = "consumer"
        requires = (GREETER,)

        def __init__(self, starts: list[str]) -> None:
            self.starts = starts

        async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
            self.starts.append(f"consumer sees {ctx.service(GREETER)}")

    async def check() -> None:
        starts: list[str] = []
        root = Context()
        await root.mount(Consumer(starts))
        source = await root.mount(Counted(starts), {"v": 1})
        await source.reload({"v": 2})
        assert starts == ["1", "consumer sees 1", "2", "consumer sees 2"]
        await root.dispose()

    run(check())


def _prompts(kernel: Kernel) -> list[str]:
    return kernel.root.service(PROMPTS)


def _registry(recorder: Recorder) -> PluginRegistry:
    registry = PluginRegistry()
    registry.register("host", PromptHost)
    registry.register("contributor", lambda: Contributor(recorder))
    return registry


def test_boot_reports_a_plugin_stuck_waiting_and_cleans_up() -> None:
    async def check() -> None:
        kernel = Kernel(_registry(Recorder()))
        with pytest.raises(BootError, match="waiting for: prompts"):
            await kernel.boot([PluginRow("c", "contributor")])
        assert kernel.root._closed
        lenient = Kernel(_registry(Recorder()))
        await lenient.boot([PluginRow("c", "contributor")], strict=False)
        assert lenient.problems() and lenient.handles["c"].state is PluginState.PENDING
        await lenient.close()

    run(check())


def test_reconfigure_changes_only_what_differs() -> None:
    async def check() -> None:
        kernel = Kernel(_registry(Recorder()))
        rows = [PluginRow("host", "host"), PluginRow("a", "contributor", {"label": "a"}), PluginRow("b", "contributor", {"label": "b"})]
        await kernel.boot(rows)
        host, a = kernel.handles["host"], kernel.handles["a"]
        prompts = kernel.root.service(PROMPTS)
        assert sorted(prompts) == ["section:a", "section:b"]

        await kernel.reconfigure([rows[0], PluginRow("a", "contributor", {"label": "a2"}), PluginRow("c", "contributor", {"label": "c"})])
        assert kernel.handles["host"] is host and kernel.handles["a"] is a
        assert sorted(_prompts(kernel)) == ["section:a2", "section:c"]
        assert "b" not in kernel.handles

        await kernel.reconfigure([rows[0], PluginRow("a", "contributor", {"label": "a2"}, disabled=True), PluginRow("c", "contributor", {"label": "c"})])
        assert kernel.root.service(PROMPTS) == ["section:c"] and a.state is PluginState.STOPPED
        await kernel.close()

    run(check())


def test_unknown_plugins_and_duplicate_ids_are_rejected_before_anything_runs() -> None:
    with pytest.raises(ConfigError, match="Unknown plugin"):
        PluginRegistry().create("os.system")
    with pytest.raises(ConfigError, match="Duplicate"):
        parse_rows({"plugins": [{"id": "a", "plugin": "x"}, {"id": "a", "plugin": "y"}]})
    with pytest.raises(ConfigError):
        parse_rows({"plugins": [{"id": "a", "plugin": "x", "disabled": "yes"}]})


def test_patches_replace_whole_config_insert_remove_and_dump_matches_what_boots(tmp_path: Path) -> None:
    rows = parse_rows({"plugins": [{"id": "host", "plugin": "host"}, {"id": "a", "plugin": "contributor", "config": {"label": "a", "extra": 1}}]})
    patched = apply_patch(rows, {"plugins": [
        {"id": "a", "config": {"label": "z"}},
        {"id": "n", "plugin": "contributor", "config": {"label": "n"}, "before": "a"},
    ]})
    assert [row.id for row in patched] == ["host", "n", "a"]
    assert dict(patched[2].config) == {"label": "z"}  # replaced, not merged
    assert [row.id for row in apply_patch(patched, {"plugins": [{"id": "n", "remove": True}]})] == ["host", "a"]
    with pytest.raises(ConfigError):
        apply_patch(rows, {"plugins": [{"id": "a", "plugin": "other"}]})
    with pytest.raises(ConfigError):
        apply_patch(rows, {"plugins": [{"id": "ghost", "remove": True}]})
    assert parse_rows(__import__("yaml").safe_load(dump_rows(patched))) == patched
