"""Google account access through the unmodified, officially supported Antigravity ACP runtime."""
from __future__ import annotations

import asyncio
import json
import signal
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.account_cli import AccountCliError, environment, executable, prepare


class GoogleAccount:
    def __init__(self, profile: Path) -> None:
        self.profile = profile
        self.process: asyncio.subprocess.Process | None = None
        self.sequence = 0
        self.answers: list[str] = []
        self.stderr: asyncio.Task[None] | None = None
        self.models: list[dict[str, str]] = []
        self.default_model = ""

    async def __aenter__(self) -> GoogleAccount:
        prepare(self.profile, "gemini")
        binary = executable("gemini")
        if not binary:
            raise AccountCliError("Install Google's official Antigravity account runtime first")
        self.process = await asyncio.create_subprocess_exec(binary, "acp", "--disable-telemetry", "--sandbox", "--include-default-customizations=false", "--gemini-dir", str(self.profile / "home/.gemini"), cwd=self.profile / "work", env=environment(self.profile, "gemini"), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=4 * 1024 * 1024, start_new_session=True)
        async def discard() -> None:
            assert self.process is not None and self.process.stderr is not None
            while await self.process.stderr.read(65536):
                # The official app can write OAuth URLs here. They are never logged or exposed.
                continue
        self.stderr = asyncio.create_task(discard())
        try:
            await self.request("initialize", {"protocolVersion": 1, "clientInfo": {"name": "nexus-agent", "title": "Alba Agent", "version": "1.0.0"}, "clientCapabilities": {}}, timeout=30)
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise AccountCliError("Google's account runtime is not running")
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
        self.sequence += 1
        request_id = self.sequence
        await self.send({"id": request_id, "method": method, "params": params})
        async def read() -> dict[str, Any]:
            assert self.process is not None and self.process.stdout is not None
            while raw := await self.process.stdout.readline():
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if message.get("id") == request_id and ("result" in message or "error" in message):
                    if "error" in message:
                        raise AccountCliError("Google could not complete this request. Finish Google sign-in and check your account access")
                    value = message.get("result", {})
                    return value if isinstance(value, dict) else {}
                if "method" in message and "id" in message:
                    # This adapter supplies text inference only. All filesystem/terminal actions
                    # belong to Nexus's existing scoped tool registry and approval gates.
                    if message["method"] == "session/request_permission":
                        await self.send({"id": message["id"], "result": {"outcome": {"outcome": "cancelled"}}})
                    else:
                        await self.send({"id": message["id"], "error": {"code": -32601, "message": "This client does not provide filesystem or terminal operations"}})
                if message.get("method") == "session/update":
                    update = message.get("params", {}).get("update", {})
                    if update.get("sessionUpdate") == "agent_message_chunk" and update.get("content", {}).get("type") == "text":
                        self.answers.append(str(update["content"].get("text", "")))
                        if sum(map(len, self.answers)) > 4 * 1024 * 1024:
                            raise AccountCliError("Google's reply exceeded the supported size")
            raise AccountCliError("Google's account runtime stopped before completing the request")
        try:
            return await asyncio.wait_for(read(), timeout)
        except TimeoutError as error:
            raise AccountCliError("Google sign-in or response timed out. Try again") from error

    async def login(self) -> None:
        await self.request("authenticate", {"methodId": "oauth-personal"}, timeout=360)

    async def new_session(self) -> dict[str, Any]:
        session = await self.request("session/new", {"cwd": str(self.profile / "work"), "mcpServers": []})
        models = session.get("models", {})
        self.models = [{"id": item["modelId"], "name": str(item.get("name") or item["modelId"])}
                       for item in models.get("availableModels", [])
                       if isinstance(item, dict) and isinstance(item.get("modelId"), str) and 0 < len(item["modelId"]) <= 120]
        self.default_model = str(models.get("currentModelId", ""))
        return session

    async def catalog(self) -> tuple[list[dict[str, str]], str]:
        if not self.models:
            await self.new_session()
        return self.models, self.default_model

    async def answer(self, prompt: str, model: str = "default") -> dict[str, Any]:
        session = await self.new_session()
        session_id = session.get("sessionId")
        if not isinstance(session_id, str):
            raise AccountCliError("Google did not create a conversation")
        if model != "default":
            if model not in {item["id"] for item in self.models}:
                raise AccountCliError("This model is no longer available on your Google account. Refresh the model list and choose again")
            await self.request("session/set_model", {"sessionId": session_id, "modelId": model})
        self.answers = []
        await self.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]})
        text = "".join(self.answers)
        if not text.strip():
            raise AccountCliError("Google did not return a final answer")
        # ACP does not guarantee usage counters; never invent them.
        return {"content": text, "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    async def close(self) -> None:
        if self.process is not None and self.process.returncode is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.stderr is not None:
            self.stderr.cancel()
            await asyncio.gather(self.stderr, return_exceptions=True)


@dataclass
class _Runtime:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    client: GoogleAccount | None = None
    users: int = 0
    expiry: asyncio.Task[None] | None = None


class GoogleAccounts:
    """Keep scoped ACP processes warm; every inference still uses a fresh conversation.

    A process has exactly one JSON-RPC reader. Different workspaces never share a
    process, queued turns are serialized, and idle processes have bounded lifetimes.
    """
    def __init__(self, idle_seconds: float = 300, capacity: int = 8) -> None:
        self.entries: dict[Path, _Runtime] = {}
        self.lock = asyncio.Lock()
        self.idle_seconds = idle_seconds
        self.capacity = capacity
        self.closed = False

    async def _expire(self, profile: Path, entry: _Runtime) -> None:
        await asyncio.sleep(self.idle_seconds)
        async with self.lock:
            if self.entries.get(profile) is not entry or entry.users:
                return
            del self.entries[profile]
        if entry.client is not None:
            await entry.client.close()

    @asynccontextmanager
    async def lease(self, profile: Path) -> AsyncIterator[GoogleAccount]:
        profile = profile.resolve()
        async with self.lock:
            if self.closed:
                raise AccountCliError("The account runtime is shutting down")
            entry = self.entries.get(profile)
            if entry is None:
                if len(self.entries) >= self.capacity:
                    raise AccountCliError("Too many Google workspaces are active. Try again after an idle connection closes")
                entry = _Runtime()
                self.entries[profile] = entry
            entry.users += 1
            if entry.expiry is not None:
                entry.expiry.cancel()
                entry.expiry = None
        try:
            async with entry.lock:
                try:
                    if entry.client is None or entry.client.process is None or entry.client.process.returncode is not None:
                        if entry.client is not None:
                            await entry.client.close()
                        entry.client = await GoogleAccount(profile).__aenter__()
                    yield entry.client
                except BaseException:
                    # A cancelled/interrupted JSON-RPC turn cannot be reused safely.
                    if entry.client is not None:
                        await entry.client.close()
                        entry.client = None
                    raise
        finally:
            async with self.lock:
                entry.users -= 1
                if not entry.users and not self.closed and self.entries.get(profile) is entry:
                    entry.expiry = asyncio.create_task(self._expire(profile, entry))

    async def catalog(self, profile: Path) -> tuple[list[dict[str, str]], str]:
        async with self.lease(profile) as client:
            return await client.catalog()

    async def answer(self, profile: Path, prompt: str, model: str = "default") -> dict[str, Any]:
        async with self.lease(profile) as client:
            return await client.answer(prompt, model)

    async def discard(self, profile: Path) -> None:
        async with self.lock:
            entry = self.entries.pop(profile.resolve(), None)
        if entry is not None:
            if entry.expiry is not None:
                entry.expiry.cancel()
                await asyncio.gather(entry.expiry, return_exceptions=True)
            async with entry.lock:
                if entry.client is not None:
                    await entry.client.close()

    async def close(self) -> None:
        self.closed = True
        await asyncio.gather(*(self.discard(profile) for profile in list(self.entries)))


class GoogleLogins:
    """Short-lived login jobs; scope and user ownership are checked on every poll/cancel."""
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    async def start(self, tenant: str, workspace: str, user: str, profile: Path, provider: str = "gemini") -> str:
        from uuid import uuid4
        import time
        owner = (tenant, workspace, user, provider)
        for identifier, job in list(self.jobs.items()):
            if job["owner"] == owner and job["status"] == "pending":
                job["task"].cancel()
                await asyncio.gather(job["task"], return_exceptions=True)
            if job["created"] < time.monotonic() - 900 and job["status"] != "pending":
                del self.jobs[identifier]
        if sum(job["status"] == "pending" for job in self.jobs.values()) >= 8:
            raise AccountCliError("Too many sign-in windows are open. Finish or cancel an existing sign-in")
        flow = uuid4().hex
        job = {"owner": owner, "status": "pending", "created": time.monotonic()}
        async def authenticate() -> None:
            try:
                if provider == "gemini":
                    async with GoogleAccount(profile) as client:
                        await client.login()
                else:
                    from app.account_cli import login
                    await login(profile, provider)
                job["status"] = "authorized"
            except asyncio.CancelledError:
                job["status"] = "cancelled"
                raise
            except (AccountCliError, OSError):
                job["status"] = "failed"
        job["task"] = asyncio.create_task(authenticate())
        self.jobs[flow] = job
        return flow

    def state(self, flow: str, tenant: str, workspace: str, user: str, provider: str = "gemini") -> str | None:
        job = self.jobs.get(flow)
        return str(job["status"]) if job is not None and job["owner"] == (tenant, workspace, user, provider) else None

    async def cancel(self, flow: str, tenant: str, workspace: str, user: str, provider: str) -> bool:
        if self.state(flow, tenant, workspace, user, provider) is None:
            return False
        self.jobs[flow]["task"].cancel()
        await asyncio.gather(self.jobs[flow]["task"], return_exceptions=True)
        return True

    async def close(self) -> None:
        tasks = [job["task"] for job in self.jobs.values() if not job["task"].done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
