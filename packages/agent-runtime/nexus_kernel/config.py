"""Plugin configuration: ordered rows, patch layers and a printable view of what will boot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped, unused-ignore]

from .context import KernelError, Plugin


class ConfigError(KernelError):
    pass


@dataclass(frozen=True)
class PluginRow:
    """One entry of the plugin list. `plugin` names a registered factory, never an import path."""

    id: str
    plugin: str
    config: Mapping[str, Any] = field(default_factory=dict)
    disabled: bool = False


class PluginRegistry:
    """Maps plugin names to factories so configuration can only ever mount code that was registered on purpose."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Plugin]] = {}

    def register(self, name: str, factory: Callable[[], Plugin]) -> None:
        if name in self._factories:
            raise ConfigError(f"Plugin '{name}' is already registered")
        self._factories[name] = factory

    def create(self, name: str) -> Plugin:
        try:
            return self._factories[name]()
        except KeyError as error:
            raise ConfigError(f"Unknown plugin '{name}'") from error

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def _row(raw: object) -> PluginRow:
    if not isinstance(raw, dict):
        raise ConfigError("Every plugin entry must be a mapping")
    identifier, plugin = raw.get("id"), raw.get("plugin")
    config = raw.get("config", {})
    if not isinstance(identifier, str) or not identifier or not isinstance(plugin, str) or not plugin:
        raise ConfigError("A plugin entry needs a non-empty 'id' and 'plugin'")
    if not isinstance(config, dict) or not all(isinstance(key, str) for key in config):
        raise ConfigError(f"Config of '{identifier}' must be a mapping with text keys")
    disabled = raw.get("disabled", False)
    if not isinstance(disabled, bool):
        raise ConfigError(f"'disabled' of '{identifier}' must be true or false")
    return PluginRow(identifier, plugin, config, disabled)


def parse_rows(data: object) -> list[PluginRow]:
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise ConfigError("Plugin configuration must be a mapping with a 'plugins' list")
    rows = [_row(item) for item in data["plugins"]]
    seen: set[str] = set()
    for row in rows:
        if row.id in seen:
            raise ConfigError(f"Duplicate plugin id '{row.id}'")
        seen.add(row.id)
    return rows


def load_rows(path: Path) -> list[PluginRow]:
    return parse_rows(yaml.safe_load(path.read_text(encoding="utf-8")))


def apply_patch(rows: list[PluginRow], data: object) -> list[PluginRow]:
    """Layer a patch on top of rows. A patch entry names a row by id and replaces its whole `config` and/or `disabled`;
    an unknown id inserts a new row (it needs `plugin`), optionally `before` another id; `remove: true` deletes a row."""
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise ConfigError("A patch must be a mapping with a 'plugins' list")
    result = list(rows)
    for raw in data["plugins"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise ConfigError("Every patch entry needs an 'id'")
        identifier = raw["id"]
        index = next((position for position, row in enumerate(result) if row.id == identifier), None)
        if raw.get("remove") is True:
            if index is None:
                raise ConfigError(f"Cannot remove unknown plugin '{identifier}'")
            del result[index]
        elif index is not None:
            current = result[index]
            if "plugin" in raw and raw["plugin"] != current.plugin:
                raise ConfigError(f"Patch cannot change the plugin behind '{identifier}'")
            merged = _row({"id": identifier, "plugin": current.plugin, "config": raw.get("config", current.config), "disabled": raw.get("disabled", current.disabled)})
            result[index] = merged
        else:
            added = _row(raw)
            before = raw.get("before")
            position = next((n for n, row in enumerate(result) if row.id == before), len(result)) if isinstance(before, str) else len(result)
            result.insert(position, added)
    return result


def build_rows(base: Path, patches: tuple[Path, ...] = ()) -> list[PluginRow]:
    rows = load_rows(base)
    for patch in patches:
        rows = apply_patch(rows, yaml.safe_load(patch.read_text(encoding="utf-8")))
    return rows


def dump_rows(rows: list[PluginRow]) -> str:
    """The exact plugin list a process would boot, in the same shape a patch edits."""
    payload = {"plugins": [{"id": row.id, "plugin": row.plugin, "config": dict(row.config), "disabled": row.disabled} for row in rows]}
    return str(yaml.safe_dump(payload, sort_keys=False))
