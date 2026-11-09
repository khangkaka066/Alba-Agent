"""Scoped PTY jobs, bounded journals and a local RPC owner shared by API/workers."""
from __future__ import annotations

import asyncio
import base64
import errno
import fcntl
import json
import logging
import hmac
import hashlib
import secrets
import os
import pty
import re
import signal
import struct
import termios
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import monotonic, time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .docker_supervisor import OutputSink, SandboxExecution
from .error_digest import digest_error
from .execution_policy import approved_commands

OUTPUT_LIMIT = 256 * 1024
PORT_PATTERN = re.compile(r"(?:https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\])|(?:localhost|127\.0\.0\.1|0\.0\.0\.0)|(?:listening|serving|port)\s*(?:at|on|=)?\s*):?([0-9]{2,5})\b", re.I)
Spawn = Callable[[str, int, str], Awaitable[asyncio.subprocess.Process]]
Interrupt = Callable[[str, int], Awaitable[None]]
Finish = Callable[[str, float], Awaitable[None]]


def detect_ports(text: str) -> tuple[int, ...]:
    return tuple(sorted({int(number) for match in re.finditer(PORT_PATTERN.pattern + r"|(?<![0-9]):([0-9]{4,5})\b", text, re.I) for number in [match.group(1) or match.group(2)] if number and 1024 <= int(number) <= 65535}))


@dataclass
class ManagedProcess:
    id: str
    process: asyncio.subprocess.Process
    master: int
    command: str
    background: bool
    started_at: float = field(default_factory=time)
    output: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=1024))
    ports: set[int] = field(default_factory=set)
    sequence: int = 0
    result: SandboxExecution | None = None
    task: asyncio.Task[None] | None = None

    def view(self) -> dict[str, Any]:
        return {"id": self.id, "pid": self.process.pid, "command": self.command, "background": self.background,
                "started_at": self.started_at, "running": self.result is None, "ports": sorted(self.ports),
                "exit_code": self.result.exit_code if self.result else None}


class ProcessManager:
    def __init__(self, control: Path, spawn: Spawn, interrupt: Interrupt | None = None) -> None:
        self.control = control
        control.mkdir(parents=True, exist_ok=True)
        secret = control / "rpc.key"
        try:
            fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as file:
                file.write(secrets.token_hex(32))
        self.secret = secret
        self.browser: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None
        self.on_background_exit: Finish | None = None
        self.spawn = spawn
        self.interrupt_remote = interrupt
        self.jobs: dict[str, ManagedProcess] = {}
        self.foreground: str | None = None
        self.closing = False
        self.events: deque[dict[str, Any]] = deque(maxlen=1024)
        self.sequence = 0
        self.server: asyncio.AbstractServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()
        self.socket = control / "terminal.sock"
        if len(os.fsencode(self.socket)) > 103:
            # A symlink in /tmp keeps the socket address short, while the target remains in the scoped control directory.
            import hashlib
            alias = Path("/tmp") / f"nx-pty-{os.getuid()}-{hashlib.sha256(str(control.resolve()).encode()).hexdigest()[:24]}"
            if alias.is_symlink() and alias.resolve() != control.resolve():
                raise ValueError("Terminal socket alias belongs to another control directory")
            if not alias.exists():
                alias.symlink_to(control.resolve(), target_is_directory=True)
            self.socket = alias / "terminal.sock"

    async def _owner(self) -> bool:
        loop = asyncio.get_running_loop()
        if self.server is not None and self._loop is loop and self.server.is_serving():
            return True
        if self.server is not None and self._loop is not loop:
            try:
                self.server.close()
            except RuntimeError:
                if self._loop is not None and not self._loop.is_closed():
                    raise
            self.server = None
        # Serialize broker election across processes. Never unlink a live owner's socket.
        with (self.control / "owner.lock").open("a") as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.02)
            try:
                reader, writer = await asyncio.open_unix_connection(str(self.socket))
            except (FileNotFoundError, ConnectionRefusedError):
                self.socket.unlink(missing_ok=True)
                self.server = await asyncio.start_unix_server(self._serve, path=str(self.socket), limit=128 * 1024)
                os.chmod(self.socket, 0o600)
                self._loop = loop
                return True
            else:
                writer.close()
                await writer.wait_closed()
                return False

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            if not line:
                return
            envelope = json.loads(line)
            encoded = str(envelope.get("request", ""))
            signature = hmac.new(self.secret.read_bytes(), encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, str(envelope.get("signature", ""))):
                raise PermissionError("Invalid terminal broker capability")
            request = json.loads(encoded)
            async def sink(stream: str, content: str) -> None:
                writer.write((json.dumps({"stream": stream, "text": content}) + "\n").encode())
                await writer.drain()
            result = await self._dispatch(str(request["method"]), request.get("args", {}), sink)
            writer.write((json.dumps({"result": result}) + "\n").encode())
            await writer.drain()
        except Exception as error:
            if not writer.is_closing():
                writer.write((json.dumps({"error": str(error), "kind": type(error).__name__}) + "\n").encode())
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def call(self, method: str, args: dict[str, Any] | None = None, sink: OutputSink | None = None) -> Any:
        async def discard(_stream: str, _content: str) -> None:
            return None
        sink = sink or discard
        if await self._owner():
            return await self._dispatch(method, args or {}, sink)
        reader, writer = await asyncio.open_unix_connection(str(self.socket), limit=8 * 1024 * 1024)
        try:
            encoded = json.dumps({"method": method, "args": args or {}})
            signature = hmac.new(self.secret.read_bytes(), encoded.encode(), hashlib.sha256).hexdigest()
            writer.write((json.dumps({"request": encoded, "signature": signature}) + "\n").encode())
            await writer.drain()
            while line := await asyncio.wait_for(reader.readline(), int((args or {}).get("timeout_seconds", 5)) + 10):
                message = json.loads(line)
                if "error" in message:
                    if message.get("kind") == "PermissionError":
                        raise PermissionError(message["error"])
                    raise ValueError(message["error"])
                if "result" in message:
                    return message["result"]
                await sink(message["stream"], message["text"])
            raise RuntimeError("Terminal owner disconnected")
        finally:
            writer.close()
            await writer.wait_closed()

    def _event(self, kind: str, **data: Any) -> None:
        self.sequence += 1
        self.events.append({"sequence": self.sequence, "type": kind, **data})

    async def _dispatch(self, method: str, args: dict[str, Any], sink: OutputSink) -> Any:
        if method == "browser":
            if self.browser is None:
                raise ValueError("No browser driver is configured")
            return await self.browser(args)
        if method == "execute":
            if self.closing:
                raise ValueError("The computer is restarting or stopping")
            if sum(job.result is None for job in self.jobs.values()) >= 16:
                raise ValueError("At most 16 processes may run in one computer")
            if self.foreground is not None:
                raise ValueError("The foreground terminal is busy; send input or interrupt it first")
            async with self._lock:
                if self.foreground is not None:
                    raise ValueError("The foreground terminal is busy")
                identifier = uuid4().hex
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 140, 0, 0))
                try:
                    approval = approved_commands.set(frozenset({str(args["command"])}) if args.get("approved") else frozenset())
                    try:
                        process = await self.spawn(str(args["command"]), slave, identifier)
                    finally:
                        approved_commands.reset(approval)
                except BaseException:
                    os.close(master)
                    raise
                finally:
                    os.close(slave)
                background = bool(args.get("background"))
                job = ManagedProcess(identifier, process, master, str(args["command"]), background)
                self.jobs[identifier] = job
                if not background:
                    self.foreground = identifier
                self._event("PROCESS_STARTED", **job.view())
                job.task = asyncio.create_task(self._collect(job, min(3600, max(1, int(args.get("timeout_seconds", 60)))), sink))
            if background:
                return {"status": "running", **job.view()}
            await asyncio.shield(job.task)
            return {"status": "completed", **asdict(job.result)} if job.result else {"status": "failed"}
        if method == "status":
            return {"processes": [job.view() for job in self.jobs.values()], "active_process_id": self.foreground,
                    "events": [event for event in self.events if event["sequence"] > int(args.get("after", 0))], "sequence": self.sequence}
        if method == "logs":
            job = self.jobs[str(args["id"])]
            return {**job.view(), "logs": list(job.output)}
        if method == "input":
            job = self.jobs[str(args.get("id") or self.foreground)]
            if job.result is not None:
                raise ValueError("Process has already exited")
            data = base64.b64decode(args["data"], validate=True)
            if len(data) > 16_384:
                raise ValueError("Terminal input exceeds 16 KiB")
            os.write(job.master, data)
            return {"ok": True}
        if method in ("interrupt", "stop"):
            identifier = str(args.get("id") or self.foreground)
            if identifier not in self.jobs:
                return {"ok": True}
            job = self.jobs[identifier]
            await self._signal(job, signal.SIGINT if method == "interrupt" else signal.SIGTERM)
            if method == "stop" and job.task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(job.task), 2)
                except asyncio.TimeoutError:
                    await self._signal(job, signal.SIGKILL)
                    await job.task
            return {"ok": True}
        if method == "dispose":
            await self._dispatch("close", args, sink)
            self.jobs.clear()
            self.events.clear()
            if self.server is not None:
                self.server.close()
                await self.server.wait_closed()
            return {"ok": True}
        if method == "close":
            async with self._lock:
                self.closing = True
                try:
                        if self.browser is not None:
                            await self.browser({"action": "close"})
                        for job in self.jobs.values():
                            if job.result is None:
                                await self._signal(job, signal.SIGKILL)
                        await asyncio.gather(*(job.task for job in self.jobs.values() if job.task is not None and not job.task.done()), return_exceptions=True)
                finally:
                    self.closing = False
            return {"ok": True}
        raise ValueError("Unknown terminal operation")

    async def _signal(self, job: ManagedProcess, sig: int) -> None:
        if job.result is not None:
            return
        if self.interrupt_remote is not None:
            await self.interrupt_remote(job.id, sig)
        try:
            os.killpg(job.process.pid, sig)
        except ProcessLookupError:
            return

    async def _collect(self, job: ManagedProcess, timeout: int, sink: OutputSink) -> None:
        started = monotonic()
        loop = asyncio.get_running_loop()
        output = {"stdout": "", "stderr": ""}
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
        os.set_blocking(job.master, False)
        def read() -> None:
            try:
                chunk = os.read(job.master, 4096)
            except BlockingIOError:
                return
            except OSError as error:
                if error.errno != errno.EIO:
                    self._event("TERMINAL_ERROR", message=str(error))
                chunk = b""
            if not chunk:
                loop.remove_reader(job.master)
                if not queue.full():
                    queue.put_nowait(None)
            elif queue.full():
                # Bound retained output without blocking the process on a disconnected viewer.
                queue.get_nowait()
                queue.put_nowait(chunk)
            else:
                queue.put_nowait(chunk)
        loop.add_reader(job.master, read)
        async def consume_pty() -> None:
            while (chunk := await queue.get()) is not None:
                await forward("stdout", chunk)
        async def forward(stream: str, data: bytes) -> None:
            text = data.decode(errors="replace").replace("\r\n", "\n")
            output[stream] = (output[stream] + text)[-OUTPUT_LIMIT:]
            job.sequence += 1
            job.output.append({"sequence": job.sequence, "stream": stream, "text": text})
            self._event("TERMINAL_OUTPUT", process_id=job.id, stream=stream, text=text)
            ports = set(sorted(set(detect_ports(output[stream][-8192:])) - job.ports)[:max(0, 16 - len(job.ports))])
            for port in ports:
                job.ports.add(port)
                self._event("SANDBOX_PORT_OPENED", process_id=job.id, port=port)
            try:
                await asyncio.wait_for(sink(stream, text), 0.25)
            except Exception:
                # A disconnected UI or event bus must never strand a child process or stop its output drain.
                return
        async def stderr() -> None:
            if job.process.stderr is not None:
                while block := await job.process.stderr.read(4096):
                    await forward("stderr", block)
        tasks = [asyncio.create_task(consume_pty()), asyncio.create_task(stderr())]
        timed_out = False
        try:
            try:
                await asyncio.wait_for(job.process.wait(), timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await self._signal(job, signal.SIGKILL)
                await job.process.wait()
            # Children can hold a PTY open after their parent exits. They may not hold an HTTP request forever.
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), 1)
            except asyncio.TimeoutError:
                await self._signal(job, signal.SIGKILL)
            code = 137 if timed_out else job.process.returncode or 0
            digest = digest_error(output["stderr"] or output["stdout"], code)
            job.result = SandboxExecution(code, output["stdout"], output["stderr"], (), monotonic() - started,
                                          error_digest=digest.as_dict() if digest else None)
            self._event("PROCESS_EXITED", **job.view(), error_digest=job.result.error_digest)
            if job.background and self.on_background_exit is not None:
                try:
                    await self.on_background_exit(job.id, job.result.elapsed_seconds)
                except Exception:
                    logging.getLogger("nexus.sandbox").exception("Background process usage could not be recorded", extra={"process_id": job.id})
        finally:
            loop.remove_reader(job.master)
            os.close(job.master)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.foreground == job.id:
                self.foreground = None
            # Keep finished journals bounded, while retaining every running process.
            for identifier in list(self.jobs):
                if len(self.jobs) <= 64:
                    break
                if self.jobs[identifier].result is not None and identifier != job.id:
                    del self.jobs[identifier]
