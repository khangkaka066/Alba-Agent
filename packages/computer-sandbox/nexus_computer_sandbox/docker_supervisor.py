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


class DockerSandboxSupervisor:
    def __init__(self, host_root: Path, image: str = "nexus-sandbox-python:3.11") -> None:
        if not host_root.is_absolute():
            raise ValueError("Sandbox root must be an absolute host-shared path")
        self._root = host_root.resolve()
        self._image = image
        self._root.mkdir(parents=True, exist_ok=True)

    async def run_python(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        run_id: UUID,
        code: str,
        verification_command: str,
        attempt: int,
        timeout_seconds: int,
        output_sink: OutputSink,
        input_files: dict[str, bytes] | None = None,
        script_label: str = "",
    ) -> SandboxExecution:
        if script_label and not re.fullmatch(r"[A-Za-z0-9_]{1,48}", script_label):
            raise ValueError("Sandbox script label must be 1-48 letters, digits or underscores")
        if attempt < 1 or timeout_seconds < 1 or timeout_seconds > 3600 or not code.strip() or not verification_command.strip():
            raise ValueError("Attempt, timeout, code, and verification command must be valid")
        if len(code.encode("utf-8")) > 131_072:
            raise ValueError("Generated code exceeds 128 KiB")
        run_dir = self._root / str(tenant_id) / str(workspace_id) / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        script_name = f"attempt_{script_label + '_' if script_label else ''}{attempt}.py"
        script = run_dir / script_name
        if script.exists():
            raise ValueError("Sandbox attempt number has already been used")
        if sum(len(content) for content in (input_files or {}).values()) > 1_048_576:
            raise ValueError("Sandbox file inputs exceed the 1 MiB workflow run limit")
        for name, content in (input_files or {}).items():
            if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("attempt_"):
                raise ValueError("Sandbox input filenames must be simple workspace names")
            if len(content) > 1_048_576:
                raise ValueError("Sandbox input file exceeds the 1 MiB workflow input limit")
            descriptor = os.open(run_dir / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as input_file:
                input_file.write(content)
        script.write_text(code, encoding="utf-8")
        container_name = f"nexus-sandbox-{run_id.hex}-{attempt}"
        command = [
            "docker", "run", "--rm", "--pull=never", "--name", container_name,
            # No network namespace connectivity prevents reaching host loopback,
            # RFC1918 services, and cloud metadata endpoints from user code.
            "--network", "none",
            "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--pids-limit", "64",
            "--memory", "2g", "--memory-swap", "2g", "--cpus", "2", "--ipc", "none",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--label", f"nexus.tenant_id={tenant_id}",
            "--label", f"nexus.workspace_id={workspace_id}",
            "--label", f"nexus.run_id={run_id}",
            "--mount", f"type=bind,src={run_dir},dst=/workspace",
            "--workdir", "/workspace", self._image,
            "/bin/sh", "-lc", f"python -u {script_name} && {verification_command}",
        ]
        started = monotonic()
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def forward(stream: asyncio.StreamReader | None, name: str, chunks: list[str]) -> None:
            if stream is None:
                raise RuntimeError("Docker output stream is unavailable")
            while chunk := await stream.read(4096):
                decoded = chunk.decode("utf-8", errors="replace")
                chunks.append(decoded)
                await output_sink(name, decoded)

        stdout_task = asyncio.create_task(forward(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(forward(process.stderr, "stderr", stderr_chunks))
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            await asyncio.gather(stdout_task, stderr_task)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise
        finally:
            cleanup = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await cleanup.wait()
        artifacts = tuple(
            sorted(str(path.relative_to(run_dir)) for path in run_dir.rglob("*")
                   if path.is_file() and not (path.name.startswith("attempt_") and path.suffix == ".py"))
        )
        return SandboxExecution(
            exit_code=process.returncode or 0,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            artifacts=artifacts,
            elapsed_seconds=monotonic() - started,
        )
