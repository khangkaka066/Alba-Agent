"""Persistent scoped computers with local Docker and injectable cloud drivers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import AsyncGenerator, Awaitable, Callable, Literal, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import AuditLog, SandboxComputer
from app.models.scope import scoped_session
from nexus_core_schema.models import RuntimeEventType

from .docker_supervisor import OutputSink, SandboxExecution

Visibility = Literal["shared", "private"]
BrowserHook = Callable[["ComputerHandle", str, dict[str, str]], Awaitable[bytes | None]]
BoundaryGuard = Callable[["ComputerAccess", str, str], Awaitable[None]]


@dataclass(frozen=True)
class ComputerAccess:
    tenant_id: UUID
    workspace_id: UUID
    bot_id: UUID | None = None
    run_id: UUID | None = None


@dataclass(frozen=True)
class ComputerHandle:
    id: UUID
    access: ComputerAccess
    visibility: Visibility
    provider: str
    external_id: str | None = None


class ComputerProvider(Protocol):
    name: str

    async def create(self, handle: ComputerHandle) -> str: ...
    async def destroy(self, handle: ComputerHandle) -> None: ...
    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution: ...
    async def upload(self, handle: ComputerHandle, path: str, content: bytes) -> None: ...
    async def download(self, handle: ComputerHandle, path: str) -> bytes: ...
    async def files(self, handle: ComputerHandle) -> tuple[str, ...]: ...
    async def screen_frame(self, handle: ComputerHandle) -> bytes | None: ...


def _relative_path(path: str) -> PurePosixPath:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or not candidate.parts or any(part in (".", "..") for part in candidate.parts):
        raise ValueError("Computer file path must remain inside the workspace")
    return candidate


class DockerSandboxProvider:
    name = "docker"

    def __init__(self, host_root: Path, image: str = "python:3.11-slim") -> None:
        if not host_root.is_absolute():
            raise ValueError("Computer root must be an absolute host-shared path")
        self._root = host_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._image = image

    def _directory(self, handle: ComputerHandle) -> Path:
        return self._root / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id)

    def _open_file(self, handle: ComputerHandle, path: str, flags: int, create_parents: bool = False) -> int:
        parts = _relative_path(path).parts
        root = self._directory(handle)
        root.mkdir(parents=True, exist_ok=True)
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                if create_parents:
                    try:
                        os.mkdir(part, dir_fd=directory_fd)
                    except FileExistsError:
                        if not stat.S_ISDIR(os.stat(part, dir_fd=directory_fd, follow_symlinks=False).st_mode):
                            raise ValueError("Computer path contains a non-directory component")
                child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = child_fd
            return os.open(parts[-1], flags | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)

    async def _docker(self, *arguments: str) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            "docker", *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def create(self, handle: ComputerHandle) -> str:
        directory = self._directory(handle)
        directory.mkdir(parents=True, exist_ok=True)
        name = f"nexus-computer-{handle.id.hex}"
        command = (
            # No network namespace connectivity prevents reaching host loopback,
            # RFC1918 services, and cloud metadata endpoints from user code.
            "create", "--pull=never", "--name", name, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "64", "--memory", "2g", "--memory-swap", "2g", "--cpus", "2",
            "--ipc", "none", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--label", f"nexus.tenant_id={handle.access.tenant_id}",
            "--label", f"nexus.workspace_id={handle.access.workspace_id}",
            "--label", f"nexus.bot_id={handle.access.bot_id or ''}",
            "--label", f"nexus.run_id={handle.access.run_id or ''}",
            "--mount", f"type=bind,src={directory},dst=/workspace",
            "--workdir", "/workspace", self._image,
            "/bin/sh", "-lc", "while :; do sleep 3600; done",
        )
        exit_code, _, stderr = await self._docker(*command)
        if exit_code != 0:
            raise RuntimeError(f"Could not create isolated computer: {stderr.strip()}")
        exit_code, _, stderr = await self._docker("start", name)
        if exit_code != 0:
            await self._docker("rm", "-f", name)
            raise RuntimeError(f"Could not start isolated computer: {stderr.strip()}")
        return name

    async def destroy(self, handle: ComputerHandle) -> None:
        if handle.external_id is None:
            raise ValueError("Computer has no provider instance")
        exit_code, _, stderr = await self._docker("rm", "-f", handle.external_id)
        if exit_code != 0 and "No such container" not in stderr:
            raise RuntimeError(f"Could not stop computer: {stderr.strip()}")

    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution:
        if handle.external_id is None or not command.strip() or not 1 <= timeout_seconds <= 3600:
            raise ValueError("Computer, command, and timeout must be valid")
        started = monotonic()
        process = await asyncio.create_subprocess_exec(
            "docker", "exec", handle.external_id, "/usr/bin/timeout", "--signal=KILL",
            f"{timeout_seconds}s", "/bin/sh", "-lc", command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}

        async def forward(reader: asyncio.StreamReader | None, stream: str) -> None:
            if reader is None:
                raise RuntimeError("Computer output stream is unavailable")
            while data := await reader.read(4096):
                decoded = data.decode(errors="replace")
                chunks[stream].append(decoded)
                await sink(stream, decoded)

        tasks = [asyncio.create_task(forward(process.stdout, "stdout")), asyncio.create_task(forward(process.stderr, "stderr"))]
        try:
            await asyncio.wait_for(process.wait(), timeout_seconds + 5)
            await asyncio.gather(*tasks)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return SandboxExecution(
            exit_code=process.returncode or 0,
            stdout="".join(chunks["stdout"]),
            stderr="".join(chunks["stderr"]),
            artifacts=await self.files(handle),
            elapsed_seconds=monotonic() - started,
        )

    async def upload(self, handle: ComputerHandle, path: str, content: bytes) -> None:
        descriptor = self._open_file(handle, path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, create_parents=True)
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)

    async def download(self, handle: ComputerHandle, path: str) -> bytes:
        descriptor = self._open_file(handle, path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ValueError("Computer path is not a regular file")
            return file.read()

    async def files(self, handle: ComputerHandle) -> tuple[str, ...]:
        root = self._directory(handle)
        return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() and not path.is_symlink() and not path.name.startswith("attempt_")))

    async def screen_frame(self, handle: ComputerHandle) -> bytes | None:
        try:
            return await self.download(handle, ".screen/frame.png")
        except FileNotFoundError:
            return None


class CloudComputerDriver(Protocol):
    async def create(self, handle: ComputerHandle) -> str: ...
    async def destroy(self, external_id: str) -> None: ...
    async def shell(self, external_id: str, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution: ...
    async def upload(self, external_id: str, path: str, content: bytes) -> None: ...
    async def download(self, external_id: str, path: str) -> bytes: ...
    async def files(self, external_id: str) -> tuple[str, ...]: ...
    async def screen_frame(self, external_id: str) -> bytes | None: ...


class CloudSandboxProvider:
    name: str

    def __init__(self, driver: CloudComputerDriver) -> None:
        self._driver = driver

    @staticmethod
    def _external(handle: ComputerHandle) -> str:
        if handle.external_id is None:
            raise ValueError("Computer has no provider instance")
        return handle.external_id

    async def create(self, handle: ComputerHandle) -> str:
        return await self._driver.create(handle)

    async def destroy(self, handle: ComputerHandle) -> None:
        await self._driver.destroy(self._external(handle))

    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution:
        return await self._driver.shell(self._external(handle), command, timeout_seconds, sink)

    async def upload(self, handle: ComputerHandle, path: str, content: bytes) -> None:
        await self._driver.upload(self._external(handle), str(_relative_path(path)), content)

    async def download(self, handle: ComputerHandle, path: str) -> bytes:
        return await self._driver.download(self._external(handle), str(_relative_path(path)))

    async def files(self, handle: ComputerHandle) -> tuple[str, ...]:
        return await self._driver.files(self._external(handle))

    async def screen_frame(self, handle: ComputerHandle) -> bytes | None:
        return await self._driver.screen_frame(self._external(handle))


class E2BProvider(CloudSandboxProvider):
    name = "e2b"


class DaytonaProvider(CloudSandboxProvider):
    name = "daytona"


class CreateOSProvider(CloudSandboxProvider):
    name = "createos"


class BoatProvider(CloudSandboxProvider):
    name = "boat"


class ComputerSandboxSupervisor:
    def __init__(
        self,
        engine: AsyncEngine,
        docker: DockerSandboxProvider | None,
        cloud_providers: tuple[ComputerProvider, ...] = (),
        browser_hook: BrowserHook | None = None,
        boundary_guard: BoundaryGuard | None = None,
    ) -> None:
        self._engine = engine
        self._providers: dict[str, ComputerProvider] = {provider.name: provider for provider in ((docker,) if docker is not None else ()) + cloud_providers}
        self._browser_hook = browser_hook
        self._boundary_guard = boundary_guard

    def add_provider(self, provider: ComputerProvider) -> Callable[[], None]:
        """Make a provider selectable by name; the returned callable withdraws it again."""
        if provider.name in self._providers:
            raise ValueError(f"Computer provider is already configured: {provider.name}")
        self._providers[provider.name] = provider

        def remove() -> None:
            if self._providers.get(provider.name) is provider:
                del self._providers[provider.name]

        return remove

    def provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def _provider(self, name: str) -> ComputerProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise ValueError(f"Computer provider is not configured: {name}") from error

    async def _audit(self, access: ComputerAccess, computer_id: UUID, action: str, details: dict[str, str | int]) -> None:
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            session.add(AuditLog(
                tenant_id=access.tenant_id, workspace_id=access.workspace_id,
                actor_id=None, action=action, target_type="computer",
                target_id=computer_id, details=details,
            ))

    @staticmethod
    def _handle(row: SandboxComputer) -> ComputerHandle:
        return ComputerHandle(
            row.id, ComputerAccess(row.tenant_id, row.workspace_id, row.bot_id, row.run_id),
            cast(Visibility, row.visibility), row.provider, row.external_id,
        )

    async def create(self, access: ComputerAccess, visibility: Visibility = "private", provider: str = "docker") -> ComputerHandle:
        if visibility == "private" and access.bot_id is None and access.run_id is None:
            raise ValueError("Private computers require a bot or run owner")
        driver = self._provider(provider)
        row = SandboxComputer(
            id=uuid4(), tenant_id=access.tenant_id, workspace_id=access.workspace_id,
            bot_id=access.bot_id, run_id=access.run_id, visibility=visibility,
            provider=provider, status="provisioning",
        )
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            session.add(row)
        handle = self._handle(row)
        try:
            external_id = await driver.create(handle)
        except Exception:
            async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
                stored = await session.get(SandboxComputer, row.id)
                if stored is not None:
                    stored.status = "failed"
            raise
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            stored = await session.get(SandboxComputer, row.id)
            if stored is None:
                raise LookupError("Provisioned computer disappeared")
            stored.status = "running"
            stored.external_id = external_id
        return ComputerHandle(handle.id, access, visibility, provider, external_id)

    async def get(self, access: ComputerAccess, computer_id: UUID) -> ComputerHandle:
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            row = await session.get(SandboxComputer, computer_id)
            if row is None or row.status != "running":
                raise LookupError("Computer is not running in this workspace")
            if row.visibility == "private" and (
                (row.bot_id is not None and row.bot_id != access.bot_id) or
                (row.run_id is not None and row.run_id != access.run_id)
            ):
                raise PermissionError("Private computer belongs to another bot or run")
            return self._handle(row)

    async def terminate(self, access: ComputerAccess, computer_id: UUID) -> None:
        handle = await self.get(access, computer_id)
        await self._provider(handle.provider).destroy(handle)
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            row = await session.get(SandboxComputer, computer_id)
            if row is not None:
                row.status = "terminated"
                session.add(AuditLog(
                    tenant_id=access.tenant_id, workspace_id=access.workspace_id,
                    actor_id=None, action="computer.terminated", target_type="computer",
                    target_id=computer_id, details={"provider": handle.provider},
                ))

    async def execute_shell(
        self, access: ComputerAccess, computer_id: UUID, command: str,
        timeout_seconds: int, sink: OutputSink, *, boundary: str | None = None,
        approval_guard: BoundaryGuard | None = None,
    ) -> SandboxExecution:
        handle = await self.get(access, computer_id)
        if boundary is None:
            try:
                tokens = shlex.split(command)
            except ValueError as error:
                raise ValueError("Shell command has invalid quoting") from error
            if any(token in ("rm", "rmdir", "mkfs", "shred", "shutdown", "reboot") for token in tokens):
                boundary = "destructive_command"
        if boundary is not None:
            guard = approval_guard or self._boundary_guard
            if guard is None:
                raise PermissionError("Sensitive computer actions require an approval guard")
            await guard(access, boundary, command)
        result = await self._provider(handle.provider).shell(handle, command, timeout_seconds, sink)
        await self._audit(access, computer_id, "computer.shell", {
            "command_sha256": hashlib.sha256(command.encode()).hexdigest(), "exit_code": result.exit_code,
        })
        return result

    async def upload(self, access: ComputerAccess, computer_id: UUID, path: str, content: bytes) -> None:
        handle = await self.get(access, computer_id)
        await self._provider(handle.provider).upload(handle, path, content)
        await self._audit(access, computer_id, "computer.upload", {"path": path, "sha256": hashlib.sha256(content).hexdigest()})

    async def download(self, access: ComputerAccess, computer_id: UUID, path: str) -> bytes:
        handle = await self.get(access, computer_id)
        content = await self._provider(handle.provider).download(handle, path)
        await self._audit(access, computer_id, "computer.download", {"path": path})
        return content

    async def browser_action(
        self, access: ComputerAccess, computer_id: UUID, action: str,
        arguments: dict[str, str], approval_guard: BoundaryGuard | None = None,
    ) -> bytes | None:
        handle = await self.get(access, computer_id)
        if action in ("send_email", "delete", "purchase", "submit_external"):
            guard = approval_guard or self._boundary_guard
            if guard is None:
                raise PermissionError("Sensitive browser actions require an approval guard")
            category = "external_email" if action == "send_email" else "destructive_command" if action == "delete" else "external_action"
            await guard(access, category, action)
        if self._browser_hook is None:
            raise RuntimeError("No browser automation driver is configured")
        frame = await self._browser_hook(handle, action, arguments)
        if frame is not None:
            await self._provider(handle.provider).upload(handle, ".screen/frame.png", frame)
        await self._audit(access, computer_id, "computer.browser", {"action": action})
        return frame

    async def screen_proxy(self, access: ComputerAccess, computer_id: UUID, interval_seconds: float = 0.2) -> AsyncGenerator[bytes, None]:
        handle = await self.get(access, computer_id)
        previous = ""
        while True:
            frame = await self._provider(handle.provider).screen_frame(handle)
            if frame is not None:
                digest = hashlib.sha256(frame).hexdigest()
                if digest != previous:
                    previous = digest
                    yield frame
            await asyncio.sleep(interval_seconds)

    async def stream_screen_events(self, access: ComputerAccess, computer_id: UUID, emitter: object) -> None:
        from callbacks.event_bus import RuntimeEventEmitter

        if not isinstance(emitter, RuntimeEventEmitter) or (
            emitter.tenant_id, emitter.workspace_id
        ) != (access.tenant_id, access.workspace_id) or (
            access.run_id is not None and emitter.run_id != access.run_id
        ):
            raise ValueError("Screen event emitter does not match computer scope")
        async for frame in self.screen_proxy(access, computer_id):
            await emitter.emit(
                RuntimeEventType.SANDBOX_SCREEN_FRAME,
                {"computer_id": str(computer_id), "mime_type": "image/png", "data_base64": base64.b64encode(frame).decode()},
            )

    async def read_run_file(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, path: str, max_bytes: int = 64 * 1024 * 1024) -> bytes:
        """Read a file the run's isolated computer produced, for export into the run artifact directory."""
        relative = _relative_path(path)
        if relative.name.startswith("attempt_"):
            raise ValueError("Generated attempt scripts are not deliverables")
        access = ComputerAccess(tenant_id, workspace_id, run_id=run_id)
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id, SandboxComputer.status == "running"))
        if row is None:
            raise FileNotFoundError("The run has no running computer")
        handle = await self.get(access, row.id)
        content = await self._provider(handle.provider).download(handle, relative.as_posix())
        if len(content) > max_bytes:
            raise ValueError("Sandbox deliverable exceeds the export size limit")
        return content

    async def run_python(
        self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, code: str,
        verification_command: str, attempt: int, timeout_seconds: int, sink: OutputSink,
        input_files: dict[str, bytes] | None = None,
        script_label: str = "",
    ) -> SandboxExecution:
        if attempt < 1 or not code.strip() or not verification_command.strip() or len(code.encode()) > 131_072:
            raise ValueError("Invalid Python attempt")
        if script_label and not re.fullmatch(r"[A-Za-z0-9_]{1,48}", script_label):
            raise ValueError("Sandbox script label must be 1-48 letters, digits or underscores")
        access = ComputerAccess(tenant_id, workspace_id, run_id=run_id)
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id, SandboxComputer.status == "running"))
        handle = await self.get(access, row.id) if row is not None else await self.create(access)
        script = f"attempt_{script_label + '_' if script_label else ''}{attempt}.py"
        provider = self._provider(handle.provider)
        if sum(len(content) for content in (input_files or {}).values()) > 1_048_576:
            raise ValueError("Sandbox file inputs exceed the 1 MiB workflow run limit")
        existing_attempt = True
        try:
            await provider.download(handle, script)
        except FileNotFoundError:
            existing_attempt = False
        if existing_attempt:
            raise ValueError("Sandbox attempt number has already been used")
        for path, content in (input_files or {}).items():
            _relative_path(path)
            await provider.upload(handle, path, content)
        await provider.upload(handle, script, code.encode())
        result = await self.execute_shell(
            access, handle.id, f"python -u {shlex.quote(script)} && {verification_command}",
            timeout_seconds, sink,
        )
        return result
