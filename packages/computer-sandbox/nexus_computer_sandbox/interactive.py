"""Interactive computer capabilities, owned by the sandbox.interactive plugin."""
from __future__ import annotations

import asyncio
import base64
import logging
import json
from typing import Any, Awaitable, Callable
from uuid import UUID

from .docker_supervisor import OutputSink, SandboxExecution
from .supervisor import BoundaryGuard, ComputerAccess, ComputerHandle, ComputerSandboxSupervisor, DockerSandboxProvider

EventSink = Callable[[ComputerAccess, str, dict[str, Any]], Awaitable[None]]


class InteractiveComputers:
    def __init__(self, supervisor: ComputerSandboxSupervisor, publish: EventSink | None = None) -> None:
        self.supervisor = supervisor
        self.publish = publish
        self._screens: dict[UUID, asyncio.Task[None]] = {}
        self._ports: dict[UUID, set[tuple[str, int]]] = {}
        self._watches: dict[UUID, asyncio.Task[None]] = {}

    async def provider(self, access: ComputerAccess, computer_id: UUID) -> tuple[ComputerHandle, DockerSandboxProvider]:
        handle = await self.supervisor.get(access, computer_id)
        provider = self.supervisor._provider(handle.provider)
        if not isinstance(provider, DockerSandboxProvider):
            raise ValueError("This provider does not expose an interactive terminal")
        provider.on_background_exit = self._finished
        return handle, provider

    async def emit(self, access: ComputerAccess, kind: str, payload: dict[str, Any]) -> None:
        if self.publish is not None and access.run_id is not None:
            await self.publish(access, kind, payload)

    async def watch(self, access: ComputerAccess, computer_id: UUID) -> None:
        if computer_id in self._watches and not self._watches[computer_id].done():
            return
        async def observe() -> None:
            cursor = 0
            handle, provider = await self.provider(access, computer_id)
            while True:
                status: dict[str, Any] = dict(await provider.terminal_status(handle, cursor))
                # Servers often print their URL before bind() completes. Retry announced ports until ownership is real.
                announced = self._ports.setdefault(computer_id, set())
                for job in status.get("processes", []):
                    if not job["running"]:
                        continue
                    for candidate in job["ports"]:
                        port = int(candidate)
                        key = (str(job["id"]), port)
                        if key in announced:
                            continue
                        try:
                            await provider.owned_port(handle, port)
                        except PermissionError:
                            continue
                        announced.add(key)
                        await self.emit(access, "SANDBOX_PORT_OPENED", {"computer_id": str(computer_id), "port": port, "process_id": job["id"]})
                        try:
                            await self.browser(access, computer_id, "navigate", {"url": f"http://127.0.0.1:{port}/"})
                        except (RuntimeError, ValueError, OSError, asyncio.TimeoutError):
                            logging.getLogger("nexus.sandbox").warning("Browser preview could not start", exc_info=True)
                cursor = int(status.get("sequence", cursor))
                await asyncio.sleep(0.4)
        self._watches[computer_id] = asyncio.create_task(observe())

    async def _finished(self, computer: ComputerHandle, identifier: str, seconds: float) -> None:
        from decimal import Decimal
        from app.billing.plans import record_sandbox_usage
        await record_sandbox_usage(self.supervisor._engine, computer.access.tenant_id, computer.access.workspace_id,
                                   Decimal(str(seconds)), run_id=computer.access.run_id, agent_name="background-process")
        await self.supervisor._audit(computer.access, computer.id, "computer.process_exited", {"process_id": identifier, "elapsed_ms": int(seconds * 1000)})

    async def stop(self, access: ComputerAccess, computer_id: UUID) -> None:
        await self._stop_screen(computer_id)
        task = self._watches.pop(computer_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._ports.pop(computer_id, None)

    async def execute(self, access: ComputerAccess, computer_id: UUID, command: str, timeout: int, sink: OutputSink,
                      background: bool = False, guard: BoundaryGuard | None = None) -> SandboxExecution:
        handle, provider = await self.provider(access, computer_id)
        await self.watch(access, computer_id)
        result = await self.supervisor.execute_shell(access, computer_id, command, timeout, sink, approval_guard=guard, background=background)
        return result

    async def status(self, access: ComputerAccess, computer_id: UUID, after: int = 0) -> dict[str, Any]:
        handle, provider = await self.provider(access, computer_id)
        result: dict[str, Any] = dict(await provider.terminal_status(handle, after))
        result["computer_id"] = str(computer_id)
        result["provider"] = handle.provider
        result["snapshots"] = (await asyncio.to_thread(provider.snapshots(handle).list))[:50]
        processes = result.get("processes", [])
        result["ports"] = []
        for port in sorted({port for job in processes if job["running"] for port in job["ports"]}):
            try:
                await provider.owned_port(handle, port)
            except PermissionError:
                continue
            result["ports"].append(port)
        result["resources"] = {"cpu_percent": None, "memory_bytes": None}
        if handle.provider == "docker" and handle.external_id:
            code, text, _ = await provider._docker("stats", "--no-stream", "--format", "{{json .}}", handle.external_id)
            if code == 0 and text.strip():
                sample = json.loads(text.splitlines()[0])
                result["resources"] = {"cpu_percent": sample.get("CPUPerc"), "memory": sample.get("MemUsage")}
        elif handle.provider == "local":
            pids = [str(job["pid"]) for job in processes if job["running"]]
            if pids:
                process = await asyncio.create_subprocess_exec("/bin/ps", "-o", "pcpu=,rss=", "-p", ",".join(pids), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                stdout, _ = await process.communicate()
                samples = [row.split() for row in stdout.decode().splitlines()]
                result["resources"] = {"cpu_percent": sum(float(row[0]) for row in samples if len(row) == 2), "memory_bytes": sum(int(row[1]) * 1024 for row in samples if len(row) == 2), "scope": "shell_processes"}
        return result

    async def input(self, access: ComputerAccess, computer_id: UUID, data: bytes, process_id: str | None = None) -> None:
        handle, provider = await self.provider(access, computer_id)
        await provider.terminal_input(handle, data, process_id)
        await self.supervisor._audit(access, computer_id, "computer.stdin", {"bytes": len(data)})

    async def control(self, access: ComputerAccess, computer_id: UUID, action: str, process_id: str | None = None) -> dict[str, object]:
        if action not in {"interrupt", "stop", "close"}:
            raise ValueError("Unsupported process action")
        handle, provider = await self.provider(access, computer_id)
        result = await provider.terminal_control(handle, action, process_id)
        await self.supervisor._audit(access, computer_id, f"computer.{action}", {"process_id": process_id or "foreground"})
        return result

    async def logs(self, access: ComputerAccess, computer_id: UUID, process_id: str) -> dict[str, Any]:
        handle, provider = await self.provider(access, computer_id)
        result: dict[str, Any] = await provider._manager(handle).call("logs", {"id": process_id})
        return result

    async def restart(self, access: ComputerAccess, computer_id: UUID) -> None:
        handle, provider = await self.provider(access, computer_id)
        await self._stop_screen(computer_id)
        await provider.terminal_control(handle, "close")
        await provider.atomic_text(handle, ".screen/frame.png", b"")
        (provider._control(handle) / "state.json").unlink(missing_ok=True)
        if handle.provider == "docker" and handle.external_id:
            code, _, error = await provider._docker("restart", handle.external_id)
            if code:
                raise RuntimeError(error)
        await self.supervisor._audit(access, computer_id, "computer.restarted", {"provider": handle.provider})

    async def restore(self, access: ComputerAccess, computer_id: UUID, snapshot_id: str) -> None:
        handle, provider = await self.provider(access, computer_id)
        await self._stop_screen(computer_id)
        await provider.terminal_control(handle, "close")
        await provider.atomic_text(handle, ".screen/frame.png", b"")
        await asyncio.to_thread(provider.snapshots(handle).restore, snapshot_id)
        await self.supervisor._audit(access, computer_id, "computer.files_restored", {"snapshot_id": snapshot_id})
        await self.emit(access, "SANDBOX_FILES_RESTORED", {"computer_id": str(computer_id), "snapshot_id": snapshot_id})

    async def _stop_screen(self, computer_id: UUID) -> None:
        task = self._screens.pop(computer_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def browser(self, access: ComputerAccess, computer_id: UUID, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handle, provider = await self.provider(access, computer_id)
        result = await provider.browser(handle, action, arguments)
        await self.supervisor._audit(access, computer_id, "computer.browser", {"action": action, "human": int(bool(arguments.get("human")))})
        if computer_id not in self._screens or self._screens[computer_id].done():
            async def frames() -> None:
                previous = ""
                while True:
                    frame = await provider.browser(handle, "frame", {})
                    encoded = str(frame.get("frame_png_base64", ""))
                    if encoded and encoded != previous:
                        previous = encoded
                        await provider.atomic_text(handle, ".screen/frame.png", base64.b64decode(encoded))
                        await self.emit(access, "SANDBOX_SCREEN_FRAME", {"computer_id": str(computer_id), "mime_type": "image/png", "data_base64": encoded})
                    await asyncio.sleep(0.3)
            self._screens[computer_id] = asyncio.create_task(frames())
        return result

    async def close(self) -> None:
        for task in (*self._watches.values(), *self._screens.values()):
            task.cancel()
        await asyncio.gather(*self._watches.values(), *self._screens.values(), return_exceptions=True)
        self._watches.clear()
        for provider in self.supervisor._providers.values():
            if isinstance(provider, DockerSandboxProvider):
                for manager in provider._managers.values():
                    if manager.server is not None:
                        await manager.call("close")
                        manager.server.close()
                        await manager.server.wait_closed()
