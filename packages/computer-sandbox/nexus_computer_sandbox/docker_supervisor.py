"""Run bounded Python tasks in tenant-labelled, networkless Docker containers."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Awaitable, Callable
from uuid import UUID

OutputSink = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class SandboxExecution:
    exit_code: int
    stdout: str
    stderr: str
    artifacts: tuple[str, ...]
    elapsed_seconds: float
    error_digest: dict[str, str] | None = None
    process_id: str | None = None
    snapshot_id: str | None = None


class DockerSandboxSupervisor:
    """Compatibility runner using the same persistent, hardened computer provider."""
    def __init__(self, host_root: Path, image: str = "nexus-sandbox-python:3.11") -> None:
        from .supervisor import DockerSandboxProvider
        self._provider = DockerSandboxProvider(host_root, image)
        self._handles: dict[tuple[UUID, UUID, UUID], object] = {}

    async def run_python(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, code: str,
                         verification_command: str, attempt: int, timeout_seconds: int, output_sink: OutputSink,
                         input_files: dict[str, bytes] | None = None, script_label: str = "") -> SandboxExecution:
        from dataclasses import replace
        from .supervisor import ComputerAccess, ComputerHandle
        from .snapshots import MAX_FILE_BYTES
        if script_label and not re.fullmatch(r"[A-Za-z0-9_]{1,48}", script_label):
            raise ValueError("Invalid sandbox script label")
        if attempt < 1 or not 1 <= timeout_seconds <= 3600 or not code.strip() or not verification_command.strip() or len(code.encode()) > 131_072:
            raise ValueError("Attempt, timeout, code and verification command must be valid")
        if sum(len(content) for content in (input_files or {}).values()) > MAX_FILE_BYTES:
            raise ValueError("Sandbox inputs exceed 500 MiB")
        for path in input_files or {}:
            parts = path.split("/")
            if len(path) > 255 or len(parts) > 8 or path.startswith("attempt_") or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", part) or part in {".", ".."} for part in parts):
                raise ValueError("Sandbox input filenames must be relative workspace paths without '..'")
        key = (tenant_id, workspace_id, run_id)
        known = self._handles.get(key)
        if isinstance(known, ComputerHandle):
            handle = known
        else:
            handle = ComputerHandle(run_id, ComputerAccess(tenant_id, workspace_id, run_id=run_id), "private", "docker")
            handle = replace(handle, external_id=await self._provider.create(handle))
            self._handles[key] = handle
        name = f"attempt_{script_label + '_' if script_label else ''}{attempt}.py"
        if (self._provider._directory(handle) / name).exists():
            raise ValueError("Sandbox attempt number has already been used")
        if sum(len(content) for content in (input_files or {}).values()) > MAX_FILE_BYTES:
            raise ValueError("Sandbox inputs exceed 500 MiB")
        for path, content in (input_files or {}).items():
            if not path or path.startswith("attempt_"):
                raise ValueError("Invalid input filename")
            await self._provider.upload(handle, path, content)
        await self._provider.upload(handle, name, code.encode())
        import shlex
        return await self._provider.shell(handle, f"python -u {shlex.quote(name)} && {verification_command}", timeout_seconds, output_sink)

    async def close(self) -> None:
        from .supervisor import ComputerHandle
        for handle in self._handles.values():
            if isinstance(handle, ComputerHandle):
                await self._provider.destroy(handle)
        self._handles.clear()
