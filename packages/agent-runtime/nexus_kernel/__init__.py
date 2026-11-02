"""Lightweight plugin kernel: scoped services, reversible registrations, dependency-driven plugin lifecycle."""

from .config import ConfigError, PluginRegistry, PluginRow, apply_patch, build_rows, dump_rows, load_rows, parse_rows
from .context import (
    Context, EventMode, EventModeError, KernelError, Plugin, PluginHandle, PluginState, ServiceConflictError, ServiceKey, ServiceMissingError,
)
from .kernel import BootError, Kernel

__all__ = [
    "BootError", "ConfigError", "Context", "EventMode", "EventModeError", "Kernel", "KernelError", "Plugin", "PluginHandle", "PluginRegistry",
    "PluginRow", "PluginState", "ServiceConflictError", "ServiceKey", "ServiceMissingError", "apply_patch", "build_rows", "dump_rows", "load_rows", "parse_rows",
]
