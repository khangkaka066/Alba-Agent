"""Account model metadata from unmodified official applications; never reads credential files."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from app.account_cli import AccountCliError, environment, executable


async def read_codex_models(profile: Path) -> tuple[list[dict[str, str]], str]:
    binary = executable("codex")
    if binary is None:
        raise AccountCliError("Install the official Codex application first")
    process = await asyncio.create_subprocess_exec(binary, "app-server", cwd=profile / "work", env=environment(profile, "codex"), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=4 * 1024 * 1024, start_new_session=True)
    async def request(identifier: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write((json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode())
        await process.stdin.drain()
        async def read() -> dict[str, Any]:
            assert process.stdin is not None and process.stdout is not None
            while raw := await process.stdout.readline():
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue  # the app server may print log lines before or between JSON messages
                if not isinstance(message, dict):
                    continue
                if message.get("id") == identifier and ("result" in message or "error" in message):
                    if "error" in message:
                        raise AccountCliError("Codex could not list the models available to this account")
                    result = message.get("result", {})
                    return result if isinstance(result, dict) else {}
                if "id" in message and "method" in message:
                    process.stdin.write((json.dumps({"id": message["id"], "error": {"code": -32601, "message": "Model discovery does not perform workspace actions"}}) + "\n").encode())
                    await process.stdin.drain()
            raise AccountCliError("Codex stopped while loading its model catalog")
        return await asyncio.wait_for(read(), 30)
    try:
        await request(1, "initialize", {"clientInfo": {"name": "alba_agent", "title": "Alba Agent", "version": "1.0.0"}})
        assert process.stdin is not None
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        response = await request(2, "model/list", {})
        models: list[dict[str, str]] = []
        default = ""
        for item in response.get("data", []):
            name = item.get("model")
            if not isinstance(name, str) or not name or len(name) > 100 or item.get("hidden"):
                continue
            label = str(item.get("displayName") or name)
            efforts = item.get("supportedReasoningEfforts") or []
            if not efforts:  # models without reasoning levels are still selectable
                models.append({"id": name, "name": label})
                if item.get("isDefault"):
                    default = name
            for choice in efforts:
                effort = choice.get("reasoningEffort")
                if effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
                    continue
                identifier = f"{name}@{effort}"
                models.append({"id": identifier, "name": f"{label} ({str(effort).capitalize()})"})
                if item.get("isDefault") and effort == item.get("defaultReasoningEffort"):
                    default = identifier
        if not models:
            raise AccountCliError("Codex did not advertise any available models")
        return models, default or models[0]["id"]
    except (TimeoutError, ValueError) as error:
        raise AccountCliError("Codex model discovery timed out or returned an invalid response") from error
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                process.kill()
                await process.wait()


class AccountModels:
    def __init__(self) -> None:
        self.entries: dict[Path, tuple[float, list[dict[str, str]], str]] = {}
        self.lock = asyncio.Lock()

    async def codex(self, profile: Path) -> tuple[list[dict[str, str]], str]:
        key = profile.resolve()
        async with self.lock:
            cached = self.entries.get(key)
            if cached and time.monotonic() - cached[0] < 300:
                return cached[1], cached[2]
            models, current = await read_codex_models(profile)
            if len(self.entries) >= 64:
                self.entries.pop(min(self.entries, key=lambda item: self.entries[item][0]))
            self.entries[key] = (time.monotonic(), models, current)
            return models, current
