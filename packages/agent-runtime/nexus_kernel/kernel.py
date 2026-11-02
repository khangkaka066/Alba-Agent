"""Boots a plugin list into a context, keeps it in step with configuration changes and shuts it down."""

from __future__ import annotations

from .config import PluginRegistry, PluginRow
from .context import Context, KernelError, PluginHandle, PluginState


class BootError(KernelError):
    pass


class Kernel:
    def __init__(self, registry: PluginRegistry, root: Context | None = None) -> None:
        self.registry = registry
        self.root = root or Context("root")
        self._rows: dict[str, PluginRow] = {}
        self._handles: dict[str, PluginHandle] = {}

    @property
    def handles(self) -> dict[str, PluginHandle]:
        return dict(self._handles)

    async def boot(self, rows: list[PluginRow], *, strict: bool = True) -> None:
        """Mount every enabled row. With `strict`, a plugin that failed or is still waiting for a service aborts the boot."""
        await self._mount(rows)
        problems = self.problems()
        if strict and problems:
            await self.close()
            raise BootError("; ".join(problems))

    async def _mount(self, rows: list[PluginRow]) -> None:
        for row in rows:
            handle = await self.root.mount(self.registry.create(row.plugin), row.config, id=row.id)
            self._rows[row.id], self._handles[row.id] = row, handle
            if row.disabled:
                await handle.stop()

    def problems(self) -> list[str]:
        found: list[str] = []
        for identifier, handle in self._handles.items():
            if self._rows[identifier].disabled:
                continue
            if handle.state is PluginState.FAILED:
                found.append(f"{identifier} failed: {handle.error}")
            elif handle.state is not PluginState.ACTIVE:
                found.append(f"{identifier} is {handle.state.value}, waiting for: {', '.join(handle.missing()) or 'a dependency'}")
        return found

    async def reconfigure(self, rows: list[PluginRow]) -> None:
        """Bring the running plugins in line with `rows`, touching only what changed. Dependents restart around a changed plugin."""
        wanted = {row.id: row for row in rows}
        for identifier in [name for name in self._handles if name not in wanted]:
            await self._handles.pop(identifier).remove()
            del self._rows[identifier]
        added: list[PluginRow] = []
        for row in rows:
            current = self._rows.get(row.id)
            if current is None:
                added.append(row)
                continue
            handle = self._handles[row.id]
            if current.plugin != row.plugin:
                await handle.remove()
                del self._handles[row.id], self._rows[row.id]
                added.append(row)
            elif current.config != row.config:
                self._rows[row.id] = row
                await handle.reload(row.config)
                if row.disabled:
                    await handle.stop()
            elif current.disabled != row.disabled:
                self._rows[row.id] = row
                await (handle.stop() if row.disabled else handle.start())
        await self._mount(added)

    async def close(self) -> None:
        """Stop every plugin newest first and release everything they registered."""
        self._handles.clear()
        self._rows.clear()
        await self.root.dispose()
