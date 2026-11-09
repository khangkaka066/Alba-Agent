"""Persistent scoped computers with local Docker and injectable cloud drivers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import json
import os
import re
import shlex
import stat
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, AsyncGenerator, AsyncIterable, Awaitable, BinaryIO, Callable, Iterator, Literal, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import AuditLog, SandboxComputer
from app.models.scope import scoped_session
from nexus_core_schema.models import RuntimeEventType

from .docker_supervisor import OutputSink, SandboxExecution
from .execution_policy import Decision, approved_commands
from .process_manager import ProcessManager
from .shell_state import CAPTURE, command_script, read_shell_state
from .snapshots import MAX_FILE_BYTES, WorkspaceSnapshots

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

    def __init__(self, host_root: Path, image: str = "nexus-sandbox-python:3.11") -> None:
        if not host_root.is_absolute():
            raise ValueError("Computer root must be an absolute host-shared path")
        self._root = host_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._image = image
        self.on_background_exit: Callable[[ComputerHandle, str, float], Awaitable[None]] | None = None
        self._managers: dict[UUID, ProcessManager] = {}

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
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("Docker daemon did not respond within 30 seconds")
        return process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def create(self, handle: ComputerHandle) -> str:
        directory = self._directory(handle)
        directory.mkdir(parents=True, exist_ok=True)
        self._control(handle).mkdir(parents=True, exist_ok=True)
        name = f"nexus-computer-{handle.id.hex}"
        code, status_text, _ = await self._docker("inspect", "--format", "{{.State.Running}}", name)
        if code == 0 and status_text.strip() == "true":
            return name
        await self._docker("rm", "-f", name)
        command = (
            # No network namespace connectivity prevents reaching host loopback,
            # RFC1918 services, and cloud metadata endpoints from user code.
            "create", "--pull=never", "--name", name, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--ulimit", "fsize=1073741824:1073741824", "--pids-limit", "256", "--memory", "2g", "--memory-swap", "2g", "--cpus", "2",
            "--ipc", "none", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--label", f"nexus.tenant_id={handle.access.tenant_id}",
            "--label", f"nexus.workspace_id={handle.access.workspace_id}",
            "--label", f"nexus.bot_id={handle.access.bot_id or ''}",
            "--label", f"nexus.run_id={handle.access.run_id or ''}",
            "--mount", f"type=bind,src={directory},dst=/workspace",
            "--mount", f"type=bind,src={self._control(handle)},dst=/nexus-control",
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
        await self._manager(handle).call("dispose")
        exit_code, _, stderr = await self._docker("rm", "-f", handle.external_id)
        if exit_code != 0 and "No such container" not in stderr:
            raise RuntimeError(f"Could not stop computer: {stderr.strip()}")

    async def run_owned_containers(self) -> tuple[tuple[str, UUID, UUID, UUID, float], ...]:
        """Containers owned by a run, as (name, tenant, workspace, run, age in seconds). Bot and shared computers are not listed."""
        exit_code, listing, _ = await self._docker("ps", "-aq", "--filter", "label=nexus.run_id")
        identifiers = listing.split()
        if exit_code != 0 or not identifiers:
            return ()
        template = '{{.Name}}|{{.Created}}|{{index .Config.Labels "nexus.tenant_id"}}|{{index .Config.Labels "nexus.workspace_id"}}|{{index .Config.Labels "nexus.run_id"}}'
        exit_code, detail, _ = await self._docker("inspect", "-f", template, *identifiers)
        if exit_code != 0:
            return ()
        now = datetime.now(timezone.utc)
        found: list[tuple[str, UUID, UUID, UUID, float]] = []
        for line in detail.splitlines():
            name, created, tenant, workspace, run = (line.split("|") + ["", "", "", "", ""])[:5]
            try:
                # Docker reports nanoseconds; datetime keeps microseconds.
                moment = datetime.fromisoformat(re.sub(r"\.(\d{6})\d*", r".\1", created.replace("Z", "+00:00")))
                found.append((name.lstrip("/"), UUID(tenant), UUID(workspace), UUID(run), (now - moment).total_seconds()))
            except ValueError:
                continue  # unlabelled or malformed: not ours to remove
        return tuple(found)

    def _control(self, handle: ComputerHandle) -> Path:
        directory = self._root / ".control" / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def snapshots(self, handle: ComputerHandle) -> WorkspaceSnapshots:
        return WorkspaceSnapshots(self._directory(handle), self._root / ".snapshots" / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id))

    async def _spawn(self, handle: ComputerHandle, command: str, slave: int, identifier: str) -> asyncio.subprocess.Process:
        if handle.external_id is None:
            raise ValueError("Computer has no container")
        control = self._control(handle)
        defaults = {"TERM": "dumb", "PAGER": "cat", "GIT_PAGER": "cat", "HOME": "/workspace/.nexus-home", "PATH": "/workspace/.nexus-home/.local/bin:/usr/local/bin:/usr/bin:/bin",
                    "PYTHONPATH": "/workspace/.nexus-packages", "PIP_TARGET": "/workspace/.nexus-packages", "NPM_CONFIG_PREFIX": "/workspace/.nexus-home/.npm",
                    "OTEL_SDK_DISABLED": "true", "CREWAI_DISABLE_TELEMETRY": "true", "NEXT_TELEMETRY_DISABLED": "1"}
        cwd, env = read_shell_state(control / "state.json", "/workspace", defaults)
        (control / "capture.py").write_text(CAPTURE)
        state_file = f"/nexus-control/{identifier}.state.json" if command.startswith("# NEXUS_BACKGROUND") else "/nexus-control/state.json"
        script = command_script(command, "/usr/local/bin/python", "/nexus-control/capture.py", state_file, "/workspace", f"/nexus-control/{identifier}.pid")
        (control / f"{identifier}.sh").write_text(script)
        environment = [part for key, value in env.items() for part in ("--env", f"{key}={value}")]
        return await asyncio.create_subprocess_exec("docker", "exec", "-it", "--workdir", cwd, *environment, handle.external_id,
            "/usr/local/bin/python", "-I", "-c", "import os; os.getsid(0) == os.getpid() or os.setsid(); os.execv('/bin/sh',['/bin/sh',__import__('sys').argv[1]])", f"/nexus-control/{identifier}.sh",
            stdin=slave, stdout=slave, stderr=asyncio.subprocess.PIPE, start_new_session=True)

    async def _interrupt(self, handle: ComputerHandle, identifier: str, sig: int) -> None:
        if handle.external_id is None:
            return
        pid_file = self._control(handle) / f"{identifier}.pid"
        try:
            pid = int(pid_file.read_text())
        except FileNotFoundError:
            return
        if pid > 1:
            await self._docker("exec", handle.external_id, "/usr/local/bin/python", "-I", "-c", f"import os; os.killpg({pid}, {int(sig)})")

    def _manager(self, handle: ComputerHandle) -> ProcessManager:
        known = self._managers.get(handle.id)
        if known is None:
            async def spawn(command: str, slave: int, identifier: str) -> asyncio.subprocess.Process:
                return await self._spawn(handle, command, slave, identifier)
            async def interrupt(identifier: str, sig: int) -> None:
                await self._interrupt(handle, identifier, sig)
            broker = self._root / ".brokers" / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id)
            known = ProcessManager(broker, spawn, interrupt if self.name == "docker" else None)
            async def finish(identifier: str, seconds: float) -> None:
                if self.on_background_exit is not None:
                    await self.on_background_exit(handle, identifier, seconds)
            known.on_background_exit = finish
            from .browser import ComputerBrowser
            async def launch() -> asyncio.subprocess.Process:
                return await self.launch_browser(handle)
            async def local_fetch(port: int, path: str, method: str, headers: dict[str, str], body: bytes | None) -> dict[str, Any]:
                return await self.preview_request(handle, port, path, method, headers, body)
            browser = ComputerBrowser(launch, local_fetch)
            known.browser = browser.action
            self._managers[handle.id] = known
        return known

    async def terminal(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink, background: bool = False) -> SandboxExecution:
        if not command.strip() or not 1 <= timeout_seconds <= 3600:
            raise ValueError("Command and timeout must be valid")
        approved = command in approved_commands.get()
        if background:
            # A detached job must not overwrite a newer foreground shell's cwd/environment.
            command = f"# NEXUS_BACKGROUND\n( {command} )"
        result = await self._manager(handle).call("execute", {"command": command, "timeout_seconds": timeout_seconds, "background": background,
            "approved": approved}, sink)
        if result.get("status") == "running":
            return SandboxExecution(0, f"Background process {result['id']} started (pid {result['pid']}).", "", await self.files(handle), 0, process_id=result["id"])
        return SandboxExecution(int(result["exit_code"]), str(result["stdout"]), str(result["stderr"]), await self.files(handle), float(result["elapsed_seconds"]), error_digest=result.get("error_digest"))

    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution:
        return await self.terminal(handle, command, timeout_seconds, sink)

    async def launch_browser(self, handle: ComputerHandle) -> asyncio.subprocess.Process:
        if handle.external_id is None:
            raise ValueError("Computer has no container")
        control = self._control(handle)
        (control / "browser_pipe.py").write_bytes(Path(__file__).with_name("browser_pipe.py").read_bytes())
        return await asyncio.create_subprocess_exec("docker", "exec", "-i", "--env", "HOME=/workspace/.nexus-home", "--env", "XDG_CACHE_HOME=/workspace/.nexus-home/cache", handle.external_id, "/usr/local/bin/python", "-I", "/nexus-control/browser_pipe.py", "/usr/bin/chromium", "/workspace/.nexus-home/browser",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=8 * 1024 * 1024, start_new_session=True)

    async def browser(self, handle: ComputerHandle, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = await self._manager(handle).call("browser", {**arguments, "action": action, "timeout_seconds": 330 if not arguments.get("human") and action not in {"screenshot", "status", "takeover"} else 30})
        return result

    async def owned_port(self, handle: ComputerHandle, port: int) -> None:
        status: dict[str, Any] = dict(await self.terminal_status(handle))
        jobs = [job for job in status.get("processes", []) if job["running"] and port in job["ports"]]
        if not jobs or not 1024 <= port <= 65535:
            raise PermissionError("Preview port is not owned by a running process in this computer")
        if self.name == "local":
            process = await asyncio.create_subprocess_exec("/usr/sbin/lsof", "-nP", "-a", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await process.communicate()
            groups = {int(job["pid"]) for job in jobs}
            for line in stdout.decode().splitlines():
                if line.startswith("p") and line[1:].isdigit():
                    try:
                        if os.getpgid(int(line[1:])) in groups:
                            return
                    except ProcessLookupError:
                        continue
            raise PermissionError("Local preview refused: listener belongs to another process or workspace")

    async def preview_request(self, handle: ComputerHandle, port: int, path: str, method: str, headers: dict[str, str], body: bytes | None) -> dict[str, Any]:
        await self.owned_port(handle, port)
        if handle.provider == "local":
            from .preview_http import request_local
            return await asyncio.to_thread(request_local, port, path, method, headers, body)
        if handle.external_id is None:
            raise ValueError("Computer has no container")
        control = self._control(handle)
        (control / "preview_http.py").write_bytes(Path(__file__).with_name("preview_http.py").read_bytes())
        process = await asyncio.create_subprocess_exec("docker", "exec", "-i", handle.external_id, "/usr/local/bin/python", "-I", "/nexus-control/preview_http.py", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=24 * 1024 * 1024)
        data = json.dumps({"port": port, "path": path, "method": method, "headers": headers, "body": base64.b64encode(body).decode() if body else None}).encode()
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(data), 20)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode:
            raise RuntimeError(stderr.decode(errors="replace")[-1000:])
        result: dict[str, Any] = json.loads(stdout)
        return result

    async def terminal_status(self, handle: ComputerHandle, after: int = 0) -> dict[str, object]:
        result: dict[str, object] = await self._manager(handle).call("status", {"after": after})
        try:
            state = json.loads((self._control(handle) / "state.json").read_text())
            result["cwd"] = state.get("cwd", "/workspace")
        except FileNotFoundError:
            result["cwd"] = str(self._directory(handle)) if self.name == "local" else "/workspace"
        return result

    async def terminal_input(self, handle: ComputerHandle, data: bytes, process_id: str | None = None) -> None:
        await self._manager(handle).call("input", {"id": process_id, "data": base64.b64encode(data).decode()})

    async def terminal_control(self, handle: ComputerHandle, action: str, process_id: str | None = None) -> dict[str, object]:
        result: dict[str, object] = await self._manager(handle).call(action, {"id": process_id})
        return result

    async def upload(self, handle: ComputerHandle, path: str, content: bytes) -> None:
        async def chunks() -> AsyncGenerator[bytes, None]:
            yield content
        await self.upload_stream(handle, path, chunks())

    async def upload_stream(self, handle: ComputerHandle, path: str, chunks: AsyncIterable[bytes]) -> tuple[int, str]:
        size = 0
        digest = hashlib.sha256()
        with self._atomic_writer(handle, path) as file:
            async for chunk in chunks:
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ValueError("Computer file exceeds 500 MiB")
                digest.update(chunk)
                await asyncio.to_thread(file.write, chunk)
        return size, digest.hexdigest()

    async def atomic_text(self, handle: ComputerHandle, path: str, content: bytes) -> None:
        with self._atomic_writer(handle, path) as file:
            file.write(content)

    @contextmanager
    def _atomic_writer(self, handle: ComputerHandle, path: str) -> Iterator[BinaryIO]:
        relative = _relative_path(path)
        self._directory(handle).mkdir(parents=True, exist_ok=True)
        directory_fd = os.open(self._directory(handle), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                try:
                    os.mkdir(part, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = child
            temporary = f".nexus-edit-{uuid4().hex}"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            try:
                try:
                    previous = os.stat(relative.name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISREG(previous.st_mode):
                        raise ValueError("Edit target must be a regular file")
                    os.fchmod(fd, stat.S_IMODE(previous.st_mode))
                except FileNotFoundError:
                    pass
                with os.fdopen(fd, "wb") as file:
                    fd = -1
                    yield file
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, relative.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            finally:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory_fd)

    async def read_bounded(self, handle: ComputerHandle, path: str, limit: int = MAX_FILE_BYTES) -> bytes:
        descriptor = self._open_file(handle, path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Computer path is not a regular file")
            if info.st_size > limit:
                raise ValueError("Computer file exceeds the operation's size limit")
            content = file.read(limit + 1)
            if len(content) > limit:
                raise ValueError("Computer file grew beyond the operation's size limit")
            return content

    async def download(self, handle: ComputerHandle, path: str) -> bytes:
        return await self.read_bounded(handle, path)

    async def files(self, handle: ComputerHandle) -> tuple[str, ...]:
        root = self._directory(handle)
        return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() and not path.is_symlink() and not path.name.startswith("attempt_") and not any(part in {".nexus-home", ".nexus-packages", "node_modules", ".venv", "__pycache__", ".git", ".screen"} for part in path.relative_to(root).parts)))

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
        self._run_users: dict[UUID, int] = {}
        self._on_command: Callable[[ComputerAccess, UUID], Awaitable[None]] | None = None
        self._on_retire: Callable[[ComputerAccess, UUID], Awaitable[None]] | None = None
        # Which provider a new computer gets when the caller does not say. Docker stays the default; "local" is an explicit choice.
        self._default_provider = os.environ.get("NEXUS_SANDBOX_PROVIDER", "docker")

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

    async def create(self, access: ComputerAccess, visibility: Visibility = "private", provider: str | None = None) -> ComputerHandle:
        if visibility == "private" and access.bot_id is None and access.run_id is None:
            raise ValueError("Private computers require a bot or run owner")
        provider = provider or self._default_provider
        driver = self._provider(provider)
        row = SandboxComputer(
            id=uuid4(), tenant_id=access.tenant_id, workspace_id=access.workspace_id,
            bot_id=access.bot_id, run_id=access.run_id, visibility=visibility,
            provider=provider, status="provisioning",
        )
        failure: Exception | None = None
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            owner = access.run_id or access.bot_id
            if owner is not None:
                # Provisioning is serialized across API and Celery processes, not only within one Python loop.
                key = int.from_bytes(hashlib.sha256(f"{access.tenant_id}:{access.workspace_id}:{owner}".encode()).digest()[:8], "big", signed=True)
                await session.execute(select(func.pg_advisory_xact_lock(key)))
                existing = await session.scalar(select(SandboxComputer).where(
                    SandboxComputer.run_id == access.run_id, SandboxComputer.bot_id == access.bot_id,
                    SandboxComputer.status == "running",
                ).order_by(SandboxComputer.created_at.desc()).limit(1))
                if existing is not None:
                    return self._handle(existing)
            session.add(row)
            await session.flush()
            handle = self._handle(row)
            try:
                external_id = await self._provision(driver, handle)
            except Exception as error:
                row.status = "failed"
                failure = error
            else:
                row.status = "running"
                row.external_id = external_id
        if failure is not None:
            raise failure
        return self._handle(row)

    @staticmethod
    async def _provision(driver: ComputerProvider, handle: ComputerHandle, attempts: int = 3) -> str:
        """Create the instance, trying again with a short pause: a busy Docker daemon often refuses once and accepts a moment later."""
        for attempt in range(1, attempts + 1):
            try:
                return await driver.create(handle)
            except RuntimeError:
                if attempt == attempts:
                    raise
                await asyncio.sleep(1.5 * attempt)
        raise RuntimeError("Computer provisioning was not attempted")

    async def _reprovision(self, access: ComputerAccess, row: SandboxComputer) -> ComputerHandle:
        """Give a run whose computer was released a fresh instance. A run owns one row, so the row is reused."""
        driver = self._provider(row.provider)
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            stored = await session.get(SandboxComputer, row.id)
            if stored is None:
                raise LookupError("Computer disappeared")
            stored.status = "provisioning"
            handle = self._handle(stored)
        try:
            external_id = await self._provision(driver, handle)
        except Exception:
            async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
                failed = await session.get(SandboxComputer, row.id)
                if failed is not None:
                    failed.status = "failed"
            raise
        async with scoped_session(self._engine, access.tenant_id, access.workspace_id) as session:
            stored = await session.get(SandboxComputer, row.id)
            if stored is None:
                raise LookupError("Provisioned computer disappeared")
            stored.status = "running"
            stored.external_id = external_id
        return ComputerHandle(handle.id, access, handle.visibility, handle.provider, external_id)

    async def acquire_run(self, run_id: UUID) -> None:
        """A node of this run starts using its computer; nodes of one run may overlap, so uses are counted."""
        self._run_users[run_id] = self._run_users.get(run_id, 0) + 1

    async def release_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        """Release one node lease. The run retains its computer and installed packages until explicit retirement."""
        remaining = self._run_users.get(run_id, 1) - 1
        if remaining > 0:
            self._run_users[run_id] = remaining
            return
        self._run_users.pop(run_id, None)
        # The workflow owns the computer; finishing one node must not discard its installed packages or shell state.

    async def retire_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, host_backed_only: bool = False) -> None:
        """Remove the run's computer now, whatever is using it. Safe to repeat; the next command re-provisions.

        A remote computer keeps the run's files, which are exported when the run's nodes finish, so between nodes only
        local (host-backed) computers are removed; `host_backed_only` says so. The end of the run removes the rest.
        """
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id, SandboxComputer.status == "running"))
        if row is None or (host_backed_only and row.provider != "docker"):
            return
        handle = self._handle(row)
        try:
            if self._on_retire is not None:
                await self._on_retire(handle.access, handle.id)
            await self._provider(handle.provider).destroy(handle)
        except Exception:
            logging.getLogger("nexus.sandbox").exception("Run computer could not be removed", extra={"run_id": str(run_id)})
            return
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            stored = await session.get(SandboxComputer, row.id)
            if stored is not None:
                stored.status = "terminated"
        await self._audit(handle.access, row.id, "computer.released", {"provider": handle.provider})

    async def reap_orphans(self, older_than_seconds: int = 14_400) -> int:
        """Remove run computers that outlived any run, such as after a crash. Returns how many were removed."""
        provider = self._providers.get("docker")
        if not isinstance(provider, DockerSandboxProvider):
            return 0
        removed = 0
        for name, tenant_id, workspace_id, run_id, age in await provider.run_owned_containers():
            if age < older_than_seconds or run_id in self._run_users:
                continue
            exit_code, _, _ = await provider._docker("rm", "-f", name)
            if exit_code != 0:
                continue
            removed += 1
            async with scoped_session(self._engine, tenant_id, workspace_id) as session:
                row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id, SandboxComputer.status == "running"))
                if row is not None:
                    row.status = "terminated"
        return removed

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
        if self._on_retire is not None:
            await self._on_retire(access, computer_id)
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
        approval_guard: BoundaryGuard | None = None, background: bool = False,
    ) -> SandboxExecution:
        handle = await self.get(access, computer_id)
        provider = self._provider(handle.provider)
        if boundary is None:
            try:
                tokens = shlex.split(command)
            except ValueError as error:
                raise ValueError("Shell command has invalid quoting") from error
            if any(token in ("rm", "rmdir", "mkfs", "shred", "shutdown", "reboot") for token in tokens):
                boundary = "destructive_command"
            else:
                # A provider with its own execution policy (the local one) can ask for a person to confirm; that reuses the same approval.
                evaluate = getattr(provider, "evaluate_command", None)
                if evaluate is not None and evaluate(command).decision is Decision.ASK:
                    boundary = "external_action"
        approval = approved_commands.set(approved_commands.get() | {command}) if boundary is not None else None
        try:
            if boundary is not None:
                guard = approval_guard or self._boundary_guard
                if guard is None:
                    raise PermissionError("Sensitive computer actions require an approval guard")
                await guard(access, boundary, command)
            on_command = getattr(self, "_on_command", None)
            if on_command is not None:
                await on_command(access, computer_id)
            snapshot_id: str | None = None
            if isinstance(provider, DockerSandboxProvider):
                status = await provider.terminal_status(handle)
                if status.get("active_process_id"):
                    raise ValueError("A command is already running; use terminal input or interrupt it")
                if not re.fullmatch(r"\s*(?:pwd|ls|cat|head|tail|grep|rg|which|echo|printf)(?:[^;&|<>`$\r\n]*)", command):
                    snapshot = await asyncio.to_thread(provider.snapshots(handle).create, hashlib.sha256(command.encode()).hexdigest())
                    snapshot_id = str(snapshot["id"])
                result = await provider.terminal(handle, command, timeout_seconds, sink, background)
                result = replace(result, snapshot_id=snapshot_id)
            elif background:
                raise ValueError("The selected provider does not support background processes")
            else:
                result = await provider.shell(handle, command, timeout_seconds, sink)
        finally:
            if approval is not None:
                approved_commands.reset(approval)
        await self._audit(access, computer_id, "computer.shell", {
            "command_sha256": hashlib.sha256(command.encode()).hexdigest(), "exit_code": result.exit_code,
        })
        return result

    async def upload(self, access: ComputerAccess, computer_id: UUID, path: str, content: bytes) -> None:
        handle = await self.get(access, computer_id)
        await self._provider(handle.provider).upload(handle, path, content)
        await self._audit(access, computer_id, "computer.upload", {"path": path, "sha256": hashlib.sha256(content).hexdigest()})

    async def upload_stream(self, access: ComputerAccess, computer_id: UUID, path: str, chunks: AsyncIterable[bytes]) -> int:
        handle = await self.get(access, computer_id)
        provider = self._provider(handle.provider)
        if isinstance(provider, DockerSandboxProvider):
            size, digest = await provider.upload_stream(handle, path, chunks)
        else:
            content = bytearray()
            async for chunk in chunks:
                content.extend(chunk)
                if len(content) > MAX_FILE_BYTES:
                    raise ValueError("Computer file exceeds 500 MiB")
            await provider.upload(handle, path, bytes(content))
            size, digest = len(content), hashlib.sha256(content).hexdigest()
        await self._audit(access, computer_id, "computer.upload", {"path": path, "sha256": digest, "bytes": size})
        return size

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

    async def read_run_file(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, path: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
        """Read a file the run's isolated computer produced, for export into the run artifact directory."""
        relative = _relative_path(path)
        if relative.name.startswith("attempt_"):
            raise ValueError("Generated attempt scripts are not deliverables")
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id, SandboxComputer.status.in_(("running", "terminated"))))
        if row is None:
            raise FileNotFoundError("The run has no computer")
        if row.status != "running" and row.provider not in {"docker", "local"}:
            raise FileNotFoundError("The run's remote computer was already removed")
        # A removed local computer still has its files: they live in a host directory, not in the container.
        content = await self._provider(row.provider).download(self._handle(row), relative.as_posix())
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
            row = await session.scalar(select(SandboxComputer).where(SandboxComputer.run_id == run_id).order_by((SandboxComputer.status == "running").desc(), SandboxComputer.created_at.desc()).limit(1))
        if row is None:
            handle = await self.create(access)
        elif row.status == "running":
            handle = await self.get(access, row.id)
        else:
            handle = await self._reprovision(access, row)
        script = f"attempt_{script_label + '_' if script_label else ''}{attempt}.py"
        provider = self._provider(handle.provider)
        if sum(len(content) for content in (input_files or {}).values()) > MAX_FILE_BYTES:
            raise ValueError("Sandbox file inputs exceed the 500 MiB run limit")
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
