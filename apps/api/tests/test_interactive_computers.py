"""Exercise the actual PTY, workspace, policy and private Chromium transport."""
from __future__ import annotations

import asyncio
import base64
import socket
import sys
import json
import time
from pathlib import Path
from uuid import uuid4
from typing import Any
from collections.abc import AsyncIterator

import pytest

from nexus_computer_sandbox import ComputerAccess, ComputerHandle, ComputerSandboxSupervisor, LocalSandboxProvider
from nexus_computer_sandbox.file_tools import ComputerFileTools
from nexus_computer_sandbox.error_digest import digest_error
from nexus_computer_sandbox.process_manager import detect_ports
from nexus_computer_sandbox.snapshots import WorkspaceSnapshots


async def discard(_stream: str, _text: str) -> None:
    return None


def test_error_evidence_and_port_detection() -> None:
    cases = [("ModuleNotFoundError: No module named 'pandas'", 1, "MISSING_PYTHON_PACKAGE"),
             ("SyntaxError: invalid syntax", 1, "SYNTAX_ERROR"),
             ("Permission denied", 1, "PERMISSION_OR_POLICY_BLOCKED"),
             ("FileNotFoundError: No such file or directory", 1, "FILE_NOT_FOUND"),
             ("sh: missing: not found", 127, "MISSING_SYSTEM_BINARY"),
             ("OSError: Address already in use", 1, "PORT_IN_USE"), ("", 137, "TIMEOUT")]
    for text, code, expected in cases:
        result = digest_error(text, code)
        assert result and result.error_category == expected
        assert len(result.root_cause_line) <= 1200
    assert digest_error("ok", 0) is None
    assert detect_ports("http://localhost:3001 127.0.0.1:5173 :8080 port 9000") == (3001, 5173, 8080, 9000)


def test_snapshot_restores_deletions_and_rejects_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = WorkspaceSnapshots(workspace, tmp_path / "snapshots")
    (workspace / "main.py").write_text("answer = 42\n")
    (workspace / "main.py").chmod(0o755)
    snapshot = store.create()
    (workspace / "main.py").unlink()
    (workspace / "extra.txt").write_text("new")
    store.restore(snapshot["id"])
    assert (workspace / "main.py").read_text() == "answer = 42\n"
    assert (workspace / "main.py").stat().st_mode & 0o777 == 0o755
    assert not (workspace / "extra.txt").exists()
    with pytest.raises(ValueError):
        store.restore("../../escape")
    (workspace / "escape").symlink_to(tmp_path / "secret")
    with pytest.raises(ValueError, match="symbolic"):
        store.create()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS kernel sandbox")
def test_real_terminal_state_stdin_interrupt_background_and_preview(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = LocalSandboxProvider(tmp_path / "computers", interpreter=Path(sys.executable))
        access = ComputerAccess(uuid4(), uuid4(), run_id=uuid4())
        handle = ComputerHandle(uuid4(), access, "private", "local")
        handle = ComputerHandle(handle.id, access, "private", "local", await provider.create(handle))
        try:
            result = await provider.shell(handle, "mkdir -p src; cd src; export NEXUS_TEST_VALUE=preserved", 10, discard)
            assert result.exit_code == 0, result.stderr
            result = await provider.shell(handle, 'printf "%s:%s" "$PWD" "$NEXUS_TEST_VALUE"', 10, discard)
            assert result.stdout.endswith("/src:preserved")
            task = asyncio.create_task(provider.shell(handle, "python3 -c 'print(input(\"Name: \"))'", 15, discard))
            for _ in range(100):
                status: dict[str, Any] = dict(await provider.terminal_status(handle))
                if status["active_process_id"]:
                    break
                await asyncio.sleep(.02)
            await provider.terminal_input(handle, b"Nexus\n")
            result = await task
            assert result.exit_code == 0 and "Nexus" in result.stdout
            task = asyncio.create_task(provider.shell(handle, "python3 -c 'import time; time.sleep(30)'", 40, discard))
            for _ in range(100):
                if (await provider.terminal_status(handle))["active_process_id"]:
                    break
                await asyncio.sleep(.02)
            await provider.terminal_control(handle, "interrupt")
            assert (await asyncio.wait_for(task, 5)).exit_code != 0
            assert (await provider.shell(handle, "echo survived", 5, discard)).stdout.strip() == "survived"
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            await provider.upload(handle, "src/index.html", (Path(__file__).parent / "fixtures/computer-preview.html").read_bytes())
            job = await provider.terminal(handle, f"python3 -u -m http.server {port} --bind 127.0.0.1", 60, discard, True)
            assert job.process_id
            for _ in range(100):
                status = dict(await provider.terminal_status(handle))
                if any(event.get("port") == port for event in status["events"]):
                    break
                await asyncio.sleep(.05)
            await provider.owned_port(handle, port)
            page = await provider.preview_request(handle, port, "/", "GET", {}, None)
            assert page["status"] == 200 and b"Ready" in base64.b64decode(page["body"])
            # Another API process connects to the existing PTY owner instead of creating its own jobs.
            second = LocalSandboxProvider(tmp_path / "computers", interpreter=Path(sys.executable))
            assert (await second.terminal_status(handle))["processes"] == status["processes"]
            with pytest.raises(PermissionError):
                await provider.owned_port(handle, port + 1)
            await provider.browser(handle, "navigate", {"url": f"http://127.0.0.1:{port}/"})
            for _ in range(40):
                if (await provider.browser(handle, "extract", {"selector": "#result"}))["text"] == "Ready":
                    break
                await asyncio.sleep(.05)
            await provider.browser(handle, "takeover", {"enabled": True})
            for kind in ("mousePressed", "mouseReleased"):
                await provider.browser(handle, "mouse", {"human": True, "x": 100, "y": 260, "type": kind})
            await provider.browser(handle, "key", {"human": True, "text": "Human takeover works"})
            for kind in ("mousePressed", "mouseReleased"):
                await provider.browser(handle, "mouse", {"human": True, "x": 550, "y": 260, "type": kind})
            frame = await provider.browser(handle, "takeover", {"enabled": False})
            Path("/tmp/nexus-real-computer-screen.png").write_bytes(base64.b64decode(frame["frame_png_base64"]))
            assert (await provider.browser(handle, "extract", {"selector": "#result"}))["text"] == "Human takeover works"
            await provider.terminal_control(handle, "stop", job.process_id)
            assert not (await provider._manager(handle).call("logs", {"id": job.process_id}))["running"]
        finally:
            await provider.destroy(handle)
    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS workspace provider")
def test_precision_tools_are_exact_atomic_scoped_and_secret_safe(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = LocalSandboxProvider(tmp_path / "computers", interpreter=Path(sys.executable))
        access = ComputerAccess(uuid4(), uuid4(), run_id=uuid4())
        handle = ComputerHandle(uuid4(), access, "private", "local", "local-test")
        await provider.create(handle)

        class ScopedFiles(ComputerSandboxSupervisor):
            def __init__(self) -> None:
                self._providers = {"local": provider}
                self._boundary_guard = None

            async def get(self, requested: ComputerAccess, computer_id: Any) -> ComputerHandle:
                if requested != access or computer_id != handle.id:
                    raise PermissionError("Wrong tenant, workspace or computer")
                return handle

            async def _audit(self, *_args: Any, **_kwargs: Any) -> None:
                return None

        tools = ComputerFileTools(ScopedFiles())
        await provider.upload(handle, "script.py", b"value = 1\nprint(value)\n")
        assert (await tools.view_file_numbered(access, handle.id, "script.py"))["content"].startswith("1: value = 1")
        edited = await tools.surgical_file_edit(access, handle.id, "script.py", "value = 1", "value = 2")
        assert "+value = 2" in edited["diff"] and edited["syntax_checked"]
        with pytest.raises(SyntaxError):
            await tools.surgical_file_edit(access, handle.id, "script.py", "value = 2", "value = (")
        assert await provider.download(handle, "script.py") == b"value = 2\nprint(value)\n"
        with pytest.raises(ValueError, match="found 2"):
            await tools.surgical_file_edit(access, handle.id, "script.py", "value", "something")
        assert (await tools.fast_workspace_search(access, handle.id, "print", "*.py"))["matches"][0]["line"] == 2
        await provider.upload(handle, ".env", b"secret=do-not-read")
        with pytest.raises(PermissionError):
            await tools.view_file_numbered(access, handle.id, ".env")
        with pytest.raises(PermissionError):
            await tools.view_file_numbered(ComputerAccess(uuid4(), access.workspace_id, run_id=access.run_id), handle.id, "script.py")
        await provider.upload(handle, "large.csv", b"x" * (3 * 1024 * 1024))
        assert len(await provider.download(handle, "large.csv")) == 3 * 1024 * 1024
        with pytest.raises(ValueError, match="size limit"):
            await tools.view_file_numbered(access, handle.id, "large.csv")
        manager = provider._manager(handle)
        await manager.call("status")
        reader, writer = await asyncio.open_unix_connection(str(manager.socket))
        writer.write(json.dumps({"method": "execute", "args": {"command": "echo escaped", "approved": True}}).encode() + b"\n")
        await writer.drain()
        assert "Invalid terminal broker capability" in (await reader.readline()).decode()
        writer.close()
        await writer.wait_closed()
        assert not manager.jobs
        await provider.destroy(handle)
    asyncio.run(scenario())


def test_preview_capability_binds_scope_port_and_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import sandbox_preview
    from fastapi import HTTPException
    monkeypatch.setenv("NEXUS_SECRET_KEY", "test-preview-secret-value-at-least-32-bytes")
    scope = ComputerAccess(uuid4(), uuid4(), run_id=uuid4())
    computer = uuid4()
    ticket = sandbox_preview.preview_ticket(scope, computer, 8080)
    assert sandbox_preview.verify_preview(ticket) == (scope, computer, 8080)
    with pytest.raises(HTTPException):
        sandbox_preview.verify_preview(ticket + "tampered")
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 601)
    with pytest.raises(HTTPException):
        sandbox_preview.verify_preview(ticket)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Chromium transport")
def test_real_chromium_private_pipe_and_takeover(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = LocalSandboxProvider(tmp_path / "computers", interpreter=Path(sys.executable))
        access = ComputerAccess(uuid4(), uuid4(), run_id=uuid4())
        handle = ComputerHandle(uuid4(), access, "private", "local")
        handle = ComputerHandle(handle.id, access, "private", "local", await provider.create(handle))
        try:
            result = await provider.browser(handle, "screenshot", {})
            assert base64.b64decode(result["frame_png_base64"]).startswith(b"\x89PNG")
            with pytest.raises(PermissionError, match="Take control"):
                await provider.browser(handle, "key", {"human": True, "text": "test"})
            assert (await provider.browser(handle, "takeover", {"enabled": True}))["human_control"]
            await provider.browser(handle, "mouse", {"human": True, "x": 20, "y": 20, "type": "mousePressed"})
            await provider.browser(handle, "key", {"human": True, "text": "Nexus"})
            assert not (await provider.browser(handle, "takeover", {"enabled": False}))["human_control"]
        finally:
            await provider.destroy(handle)
    asyncio.run(scenario())


def test_browser_uses_private_key_storage_without_extra_network_sandbox_override() -> None:
    from nexus_computer_sandbox import browser_pipe
    launch = Path(browser_pipe.__file__).read_text()
    assert '"--use-mock-keychain"' in launch
    assert "NetworkServiceSandbox" not in launch


def test_streamed_upload_is_atomic_and_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_computer_sandbox import DockerSandboxProvider
    from nexus_computer_sandbox import supervisor as module

    async def scenario() -> None:
        provider = DockerSandboxProvider(tmp_path)
        handle = ComputerHandle(uuid4(), ComputerAccess(uuid4(), uuid4()), "shared", "docker", "file-only-test")
        await provider.upload(handle, "data.csv", b"original")
        monkeypatch.setattr(module, "MAX_FILE_BYTES", 16)

        async def oversized() -> AsyncIterator[bytes]:
            yield b"x" * 10
            yield b"y" * 10

        with pytest.raises(ValueError, match="500 MiB"):
            await provider.upload_stream(handle, "data.csv", oversized())
        assert await provider.download(handle, "data.csv") == b"original"
        assert not list(provider._directory(handle).glob(".nexus-edit-*"))
    asyncio.run(scenario())


def test_agent_browser_tool_cannot_claim_human_control(tmp_path: Path) -> None:
    from nexus_builtin_tools import BuiltinToolRegistry, ToolContext
    received: list[dict[str, str]] = []

    async def browser(action: str, arguments: dict[str, str]) -> dict[str, str]:
        assert action == "navigate"
        received.append(arguments)
        return {"status": "ok"}

    async def scenario() -> None:
        registry = BuiltinToolRegistry(ToolContext("tenant", "workspace", "run", tmp_path, browser=browser))
        await registry.run("browser_automation", {"action": "navigate", "arguments": {
            "url": "https://example.org/", "action": "takeover", "human": True, "approved": True,
        }})
        assert received == [{"url": "https://example.org/"}]
        with pytest.raises(ValueError, match="Unsupported browser action"):
            await registry.run("browser_automation", {"action": "takeover", "arguments": {"enabled": True}})
    asyncio.run(scenario())


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS process-group ownership")
def test_port_preview_waits_for_the_announced_server_to_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus_computer_sandbox.interactive import InteractiveComputers

    async def scenario() -> None:
        provider = LocalSandboxProvider(tmp_path / "computers", interpreter=Path(sys.executable))
        access = ComputerAccess(uuid4(), uuid4(), run_id=uuid4())
        handle = ComputerHandle(uuid4(), access, "private", "local", "local-test")
        await provider.create(handle)
        emitted: list[tuple[str, dict[str, Any]]] = []

        class Scoped(ComputerSandboxSupervisor):
            def __init__(self) -> None:
                self._providers = {"local": provider}

            async def get(self, requested: ComputerAccess, computer_id: Any) -> ComputerHandle:
                assert requested == access and computer_id == handle.id
                return handle

        async def publish(scope: ComputerAccess, kind: str, payload: dict[str, Any]) -> None:
            assert scope == access
            emitted.append((kind, payload))

        async def no_browser(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

        async def recorded_exit(*_args: Any, **_kwargs: Any) -> None:
            return None

        service = InteractiveComputers(Scoped(), publish)
        monkeypatch.setattr(service, "browser", no_browser)
        monkeypatch.setattr(service, "_finished", recorded_exit)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        await provider.upload(handle, "server.py", (
            f"import time,http.server\nprint('http://127.0.0.1:{port}',flush=True)\n"
            f"time.sleep(.8)\nhttp.server.HTTPServer(('127.0.0.1',{port}),http.server.SimpleHTTPRequestHandler).serve_forever()\n"
        ).encode())
        try:
            await service.watch(access, handle.id)
            await provider.terminal(handle, "python3 -u server.py", 20, discard, True)
            await asyncio.sleep(.15)
            assert not emitted
            assert (await service.status(access, handle.id))["ports"] == []
            for _ in range(50):
                if emitted:
                    break
                await asyncio.sleep(.1)
            assert len(emitted) == 1 and emitted[0][0] == "SANDBOX_PORT_OPENED"
            assert emitted[0][1]["port"] == port
        finally:
            await service.stop(access, handle.id)
            await provider.destroy(handle)
    asyncio.run(scenario())
