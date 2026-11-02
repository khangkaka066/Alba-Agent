"""Plugin container: scoped services, reversible registrations and a plugin lifecycle that follows service dependencies.

The kernel knows nothing about models, tools or sandboxes. A plugin is a unit that, once mounted, contributes services,
event listeners and other effects to a context; everything it contributed is removed when it stops, and plugins that need a
service wait for it and stop again if it disappears.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")

log = logging.getLogger("nexus.kernel")

Disposer = Callable[[], Awaitable[None] | None]
Listener = Callable[..., Any]


class KernelError(Exception):
    """Base class for container errors."""


class ServiceMissingError(KernelError):
    pass


class ServiceConflictError(KernelError):
    pass


class EventModeError(KernelError):
    pass


@dataclass(frozen=True)
class ServiceKey(Generic[T]):
    """A typed, named slot in a context. Consumers import the key, never the implementation behind it."""

    name: str

    def __str__(self) -> str:
        return self.name


class EventMode(str, Enum):
    EMIT = "emit"  # fire and forget; listeners observe
    PARALLEL = "parallel"  # awaited; all listeners run at once
    SERIAL = "serial"  # awaited; listeners run in order and their results are returned
    WATERFALL = "waterfall"  # listeners wrap each other and may short-circuit by not calling next
    BAIL = "bail"  # listeners run in order until one returns a value


class PluginState(str, Enum):
    PENDING = "pending"  # enabled, but a required service is not available yet
    LOADING = "loading"
    ACTIVE = "active"
    DISPOSING = "disposing"
    STOPPED = "stopped"  # disabled or explicitly stopped
    FAILED = "failed"


class Plugin(ABC):
    """A unit of capability. `requires` services must exist before `apply` runs; `optional` ones are used when present."""

    name: ClassVar[str]
    requires: ClassVar[tuple[ServiceKey[Any], ...]] = ()
    optional: ClassVar[tuple[ServiceKey[Any], ...]] = ()

    @abstractmethod
    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        """Register services, listeners and effects on `ctx`. Everything registered is undone when the plugin stops."""


@dataclass
class _Shared:
    """State common to a whole context tree."""

    events: dict[str, EventMode] = field(default_factory=dict)
    handles: list[PluginHandle] = field(default_factory=list)
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    dirty: bool = False
    settling: bool = False


@dataclass
class _Registered:
    listener: Listener
    owner: Context


async def _call(function: Callable[..., Any], *args: Any) -> Any:
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


class Context:
    """A scope of services and listeners. Child scopes see their parents' services; a plugin's context contributes to the scope it was mounted in."""

    def __init__(self, name: str = "root", parent: Context | None = None, *, _plugin: bool = False) -> None:
        self.name = name
        self.parent = parent
        self._plugin = _plugin
        self._home: Context = parent._home if (parent is not None and _plugin) else self
        self._shared: _Shared = parent._shared if parent is not None else _Shared()
        self._services: dict[str, Any] = {}
        self._listeners: dict[str, list[_Registered]] = {}
        self._disposers: list[Disposer] = []
        self._children: list[Context] = []
        self._handles: list[PluginHandle] = []
        self._closed = False
        if parent is not None and not _plugin:
            parent._children.append(self)

    # ---- services -------------------------------------------------------------------------------------------------

    def _chain(self) -> list[Context]:
        homes: list[Context] = []
        scope: Context | None = self._home
        while scope is not None:
            homes.append(scope)
            scope = scope.parent._home if scope.parent is not None else None
        return homes

    def provide(self, key: ServiceKey[T], service: T) -> Disposer:
        """Publish a service in this scope. It is withdrawn when the providing context is disposed."""
        self._ensure_open()
        home = self._home
        if key.name in home._services:
            raise ServiceConflictError(f"Service '{key}' is already provided in scope '{home.name}'")
        home._services[key.name] = service
        self._shared.dirty = True

        def withdraw() -> None:
            if home._services.get(key.name) is service:
                del home._services[key.name]
                self._shared.dirty = True

        self._disposers.append(withdraw)
        return withdraw

    def maybe(self, key: ServiceKey[T]) -> T | None:
        for scope in self._chain():
            if key.name in scope._services:
                found: T = scope._services[key.name]
                return found
        return None

    def has(self, key: ServiceKey[Any]) -> bool:
        return any(key.name in scope._services for scope in self._chain())

    def service(self, key: ServiceKey[T]) -> T:
        found = self.maybe(key)
        if found is None:
            raise ServiceMissingError(f"Service '{key}' is not available in scope '{self.name}'")
        return found

    # ---- reversible registrations ---------------------------------------------------------------------------------

    def on_dispose(self, disposer: Disposer) -> None:
        """Run `disposer` when this context is disposed; disposers run in reverse registration order."""
        self._ensure_open()
        self._disposers.append(disposer)

    def effect(self, setup: Callable[[], Disposer | None]) -> None:
        """Apply a registration now and keep the disposer it returns for teardown."""
        disposer = setup()
        if disposer is not None:
            self.on_dispose(disposer)

    def scope(self, name: str) -> Context:
        """A child scope with its own services, for example one per workspace or per run."""
        self._ensure_open()
        return Context(name, self)

    # ---- events ---------------------------------------------------------------------------------------------------

    def declare_event(self, name: str, mode: EventMode) -> None:
        """Fix the dispatch mode of an event so a producer and its consumers cannot disagree."""
        existing = self._shared.events.setdefault(name, mode)
        if existing is not mode:
            raise EventModeError(f"Event '{name}' is already declared as {existing.value}")

    def on(self, event: str, listener: Listener, *, prepend: bool = False) -> Disposer:
        self._ensure_open()
        home = self._home
        entry = _Registered(listener, self)
        bucket = home._listeners.setdefault(event, [])
        if prepend:
            bucket.insert(0, entry)
        else:
            bucket.append(entry)

        def remove() -> None:
            if entry in bucket:
                bucket.remove(entry)

        self._disposers.append(remove)
        return remove

    def _listeners_for(self, event: str, mode: EventMode) -> list[Listener]:
        declared = self._shared.events.get(event)
        if declared is not None and declared is not mode:
            raise EventModeError(f"Event '{event}' is declared as {declared.value}, not {mode.value}")
        ordered: list[Listener] = []
        for scope in reversed(self._chain()):
            ordered.extend(entry.listener for entry in scope._listeners.get(event, ()))
        return ordered

    def emit(self, event: str, *args: Any) -> None:
        """Notify listeners without waiting. Asynchronous listeners run as tracked tasks that are cancelled on shutdown."""
        for listener in self._listeners_for(event, EventMode.EMIT):
            try:
                result = listener(*args)
            except Exception:  # noqa: BLE001 - one broken observer must not stop the others
                log.exception("Listener for '%s' failed", event)
                continue
            if inspect.isawaitable(result):
                task = asyncio.ensure_future(result)
                self._shared.tasks.add(task)
                task.add_done_callback(functools.partial(self._finished, event=event))

    def _finished(self, task: asyncio.Task[Any], *, event: str) -> None:
        self._shared.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("Listener for '%s' failed", event, exc_info=task.exception())

    async def parallel(self, event: str, *args: Any) -> None:
        listeners = self._listeners_for(event, EventMode.PARALLEL)
        outcomes = await asyncio.gather(*(_call(listener, *args) for listener in listeners), return_exceptions=True)
        failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        if failures:
            raise ExceptionGroup(f"Listeners for '{event}' failed", failures)

    async def serial(self, event: str, *args: Any) -> list[Any]:
        return [await _call(listener, *args) for listener in self._listeners_for(event, EventMode.SERIAL)]

    async def bail(self, event: str, *args: Any) -> Any | None:
        for listener in self._listeners_for(event, EventMode.BAIL):
            result = await _call(listener, *args)
            if result is not None:
                return result
        return None

    async def waterfall(self, event: str, *args: Any, terminal: Callable[..., Awaitable[R] | R]) -> R:
        """Run listeners as nested middleware around `terminal`. A listener receives `(*args, next)`; `next(*replacement)`
        continues with the same or replaced arguments, and returning without calling it short-circuits the chain."""
        listeners = self._listeners_for(event, EventMode.WATERFALL)

        async def run(index: int, current: tuple[Any, ...]) -> R:
            if index == len(listeners):
                return cast(R, await _call(terminal, *current))

            async def forward(*replacement: Any) -> R:
                return await run(index + 1, replacement or current)

            return cast(R, await _call(listeners[index], *current, forward))

        return await run(0, args)

    # ---- plugins --------------------------------------------------------------------------------------------------

    async def mount(self, plugin: Plugin, config: Mapping[str, Any] | None = None, *, id: str | None = None) -> PluginHandle:
        """Register a plugin and start it as soon as its required services exist. A failure is recorded on the handle."""
        self._ensure_open()
        handle = PluginHandle(id or plugin.name, plugin, dict(config or {}), self)
        self._handles.append(handle)
        self._shared.handles.append(handle)
        await self.settle()
        return handle

    async def settle(self) -> None:
        """Start plugins whose requirements are met and stop those whose requirements vanished, until nothing changes."""
        shared = self._shared
        if shared.settling:
            shared.dirty = True  # called from inside a plugin's apply: the running pass will pick the change up
            return
        async with shared.lock:
            shared.settling = True
            try:
                shared.dirty = True
                while shared.dirty:
                    shared.dirty = False
                    for handle in list(shared.handles):
                        await handle._reconcile()
            finally:
                shared.settling = False

    async def dispose(self) -> None:
        """Undo everything this context and its descendants registered, newest first. Errors are collected, not fatal."""
        if self._closed:
            return
        self._closed = True
        errors: list[Exception] = []
        for handle in reversed(list(self._handles)):
            try:
                await handle._discard()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        for child in reversed(list(self._children)):
            try:
                await child.dispose()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        for disposer in reversed(self._disposers):
            try:
                outcome = disposer()
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception as error:  # noqa: BLE001
                log.exception("Disposer failed in '%s'", self.name)
                errors.append(error)
        self._disposers.clear()
        if self.parent is not None and self in self.parent._children:
            self.parent._children.remove(self)
        if self.parent is None:
            tasks = [task for task in self._shared.tasks if not task.done()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._shared.dirty = True
        if errors:
            raise ExceptionGroup(f"Disposing '{self.name}' failed", errors)

    def _ensure_open(self) -> None:
        if self._closed:
            raise KernelError(f"Context '{self.name}' is disposed")


class PluginHandle:
    """Lifecycle record of one mounted plugin."""

    def __init__(self, id: str, plugin: Plugin, config: dict[str, Any], parent: Context) -> None:
        self.id = id
        self.plugin = plugin
        self.config = config
        self.parent = parent
        self.state = PluginState.PENDING
        self.error: BaseException | None = None
        self.disposal_errors: list[BaseException] = []
        self.scope: Context | None = None
        self._wanted = True
        self._optional_seen: tuple[bool, ...] = ()

    def missing(self) -> tuple[str, ...]:
        return tuple(key.name for key in self.plugin.requires if not self.parent.has(key))

    def _optional_signature(self) -> tuple[bool, ...]:
        return tuple(self.parent.has(key) for key in self.plugin.optional)

    async def _reconcile(self) -> None:
        if self.state in (PluginState.FAILED, PluginState.LOADING, PluginState.DISPOSING):
            return
        satisfied = self._wanted and not self.missing()
        if self.state is PluginState.ACTIVE:
            if not satisfied or self._optional_signature() != self._optional_seen:
                await self._unload()
        elif self.state in (PluginState.PENDING, PluginState.STOPPED) and satisfied:
            await self._load()
        elif self.state is PluginState.STOPPED and self._wanted:
            self.state = PluginState.PENDING

    async def _load(self) -> None:
        scope = Context(f"plugin:{self.id}", self.parent, _plugin=True)
        self.scope, self.state, self.error = scope, PluginState.LOADING, None
        self._optional_seen = self._optional_signature()
        try:
            await self.plugin.apply(scope, self.config)
        except Exception as error:  # noqa: BLE001 - a plugin that cannot start must not take the process down
            log.exception("Plugin '%s' failed to start", self.id)
            self.error = error
            await self._teardown(scope)
            self.state = PluginState.FAILED
        else:
            self.state = PluginState.ACTIVE

    async def _teardown(self, scope: Context) -> None:
        try:
            await scope.dispose()
        except ExceptionGroup as group:
            self.disposal_errors.extend(group.exceptions)
        self.scope = None
        self.parent._shared.dirty = True

    async def _unload(self) -> None:
        scope = self.scope
        self.state = PluginState.DISPOSING
        if scope is not None:
            await self._teardown(scope)
        self.state = PluginState.PENDING if self._wanted else PluginState.STOPPED

    async def _discard(self) -> None:
        """Stop for good and leave the registry; used when the owning context is disposed."""
        self._wanted = False
        if self.state is PluginState.ACTIVE:
            await self._unload()
        self.state = PluginState.STOPPED
        shared = self.parent._shared
        if self in shared.handles:
            shared.handles.remove(self)
        if self in self.parent._handles:
            self.parent._handles.remove(self)

    async def stop(self) -> None:
        """Disable the plugin and withdraw everything it registered."""
        self._wanted = False
        await self.parent.settle()

    async def start(self) -> None:
        self._wanted = True
        if self.state is PluginState.FAILED:
            self.state = PluginState.PENDING
        await self.parent.settle()

    async def reload(self, config: Mapping[str, Any] | None = None) -> None:
        """Restart with new configuration; plugins that depend on this one restart around it."""
        self._wanted = False
        await self.parent.settle()
        if config is not None:
            self.config = dict(config)
        await self.start()

    async def remove(self) -> None:
        """Stop and forget this plugin."""
        self._wanted = False
        await self.parent.settle()
        await self._discard()
        self.parent._shared.dirty = True
