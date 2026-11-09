"""Official provider CLIs, isolated per local workspace. Never imports a user's login tokens.

The desktop opens the login command in the system terminal. Model calls use the same
unmodified program with its built-in tools disabled. Only final answers leave this module.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import Any
from uuid import UUID

PROVIDERS = {
    "codex": {"preset": "openai_subscription", "provider": "openai", "name": "Codex", "binary": "codex", "url": "https://developers.openai.com/codex/cli/"},
    "claude": {"preset": "claude_subscription", "provider": "anthropic", "name": "Claude", "binary": "claude", "url": "https://code.claude.com/docs/en/setup"},
    "gemini": {"preset": "gemini_subscription", "provider": "gemini", "name": "Gemini", "binary": "agy", "url": "https://antigravity.google/docs/getting-started/"},
}
ALIAS_PREFIX = "nexus-account-"
MAX_OUTPUT = 4 * 1024 * 1024


class AccountCliError(RuntimeError):
    """A safe, user-facing error. CLI stdout/stderr must never become an error message."""


class AccountCliRateLimited(AccountCliError):
    """Authentication succeeded but the provider currently refuses inference with 429."""


def executable(provider: str) -> str | None:
    if provider not in PROVIDERS:
        return None
    name = PROVIDERS[provider]["binary"]
    configured = os.environ.get(f"NEXUS_ACCOUNT_{provider.upper()}_BIN")
    tools = os.environ.get("NEXUS_ACCOUNT_TOOLS_DIR")
    managed = str(Path(tools) / "node_modules/.bin" / name) if tools else None
    official = str(Path(os.environ["NEXUS_ACCOUNT_CLI_DIR"]).parent / "official-tools" / name) if os.environ.get("NEXUS_ACCOUNT_CLI_DIR") else None
    candidates = [configured, official, managed, shutil.which(name), f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}", str(Path.home() / ".local/bin" / name)]
    return next((str(Path(value).absolute()) for value in candidates if value and Path(value).is_file() and os.access(value, os.X_OK)), None)


def profile_for(tenant: UUID, workspace: UUID, provider: str) -> Path:
    if provider not in PROVIDERS:
        raise ValueError("Unknown account provider")
    root = Path(os.environ.get("NEXUS_ACCOUNT_CLI_DIR", "/var/lib/nexus/account-clis")).resolve()
    path = root / str(tenant) / str(workspace) / provider
    # A profile can never be redirected onto another workspace or a user's real CLI home.
    if path.resolve() != path:
        raise AccountCliError("The account profile location is invalid")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (path, path / "home", path / "work", path / "config", path / "cache"):
        if directory.resolve() != directory:
            raise AccountCliError("The account profile location is invalid")
        directory.mkdir(exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    return path


def environment(profile: Path, provider: str) -> dict[str, str]:
    # A child gets a real isolated home; the parent/user environment is never changed.
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "TERM", "COLORTERM"}}
    tools = os.environ.get("NEXUS_ACCOUNT_TOOLS_DIR")
    if tools:
        env["PATH"] = str(Path(tools).parent / "node/bin") + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    env.update({"HOME": str(profile / "home"), "USERPROFILE": str(profile / "home"), "XDG_CONFIG_HOME": str(profile / "config"), "XDG_CACHE_HOME": str(profile / "cache"),
                "CODEX_HOME": str(profile / "codex"), "CLAUDE_CONFIG_DIR": str(profile / "claude"), "GEMINI_CLI_HOME": str(profile / "home"),
                "OTEL_SDK_DISABLED": "true", "DO_NOT_TRACK": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "GEMINI_TELEMETRY_ENABLED": "false"})
    return env


def prepare(profile: Path, provider: str) -> None:
    if provider == "codex":
        folder = profile / "codex"
        folder.mkdir(exist_ok=True, mode=0o700)
        config = folder / "config.toml"
        if not config.exists():
            config.write_text('cli_auth_credentials_store = "file"\n[analytics]\nenabled = false\n[feedback]\nenabled = false\n')
            config.chmod(0o600)
    elif provider == "gemini":
        folder = profile / "home/.gemini/antigravity-cli"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings = folder / "settings.json"
        if not settings.exists():
            settings.write_text(json.dumps({
                "auth": {"type": "oauth-personal"}, "disableTelemetry": True, "toolPermission": "strict",
                "permissions": {"deny": [f"{action}(*)" for action in ("read_file", "write_file", "read_url", "execute_url", "command", "unsandboxed", "mcp")]},
            }))
            settings.chmod(0o600)

def command(provider: str, operation: str, model: str = "default") -> list[str]:
    binary = executable(provider)
    if not binary:
        raise AccountCliError(f"Install the official {PROVIDERS[provider]['name']} application first, then try again")
    if provider == "gemini":
        raise AccountCliError("Use the Google account browser sign-in inside Alba Agent")
    if operation == "login":
        return [binary, *{"codex": ["login"], "claude": ["auth", "login", "--claudeai"]}[provider]]
    if provider == "codex":
        args = [binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--ignore-rules", "-c", "features.shell_tool=false", "-c", "features.unified_exec=false", "-c", "features.apply_patch_freeform=false", "-c", 'web_search="disabled"', "-"]
        if "@" in model:
            model, effort = model.rsplit("@", 1)
            if effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}:
                raise AccountCliError("Unsupported Codex effort")
            args += ["-c", f'model_reasoning_effort="{effort}"']
    elif provider == "claude":
        args = [binary, "--print", "--output-format", "json", "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "", "--no-session-persistence", "--disable-slash-commands"]
    else:
        raise AccountCliError("Unknown account provider")
    if model != "default":
        args += ["--model", model]
    return args


async def bounded_read(stream: asyncio.StreamReader | None) -> bytes:
    if stream is None:
        return b""
    result = bytearray()
    while chunk := await stream.read(65536):
        result.extend(chunk)
        if len(result) > MAX_OUTPUT:
            raise AccountCliError("The provider response exceeded the supported size")
    return bytes(result)


async def login(profile: Path, provider: str) -> None:
    """Let the unmodified official app own browser OAuth and credential storage."""
    prepare(profile, provider)
    process = await asyncio.create_subprocess_exec(*command(provider, "login"), cwd=profile / "work", env=environment(profile, provider), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try:
        # Output can contain authorization URLs. It is drained but never logged or returned.
        await asyncio.wait_for(asyncio.gather(bounded_read(process.stdout), bounded_read(process.stderr), process.wait()), 360)
        if process.returncode:
            raise AccountCliError("The official application did not complete sign-in. Try again in your browser")
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


async def authenticated(profile: Path, provider: str) -> bool:
    if provider != "claude":
        return False
    binary = executable(provider)
    if not binary:
        return False
    process = await asyncio.create_subprocess_exec(binary, "auth", "status", cwd=profile / "work", env=environment(profile, provider), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        raw, _ = await asyncio.wait_for(process.communicate(), 15)
        status = json.loads(raw)
        return process.returncode == 0 and status.get("loggedIn") is True and status.get("authMethod") == "claude.ai"
    except (ValueError, TimeoutError):
        return False
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


_execution_slots = asyncio.Semaphore(2)


async def run(profile: Path, provider: str, prompt: str, model: str = "default") -> dict[str, Any]:
    async with _execution_slots:
        return await _run(profile, provider, prompt, model)


async def _run(profile: Path, provider: str, prompt: str, model: str = "default") -> dict[str, Any]:
    if provider == "gemini":
        from app.google_account import GoogleAccount
        async with GoogleAccount(profile) as account:
            return await account.answer(prompt, model)
    prepare(profile, provider)
    process = await asyncio.create_subprocess_exec(*command(provider, "complete", model), cwd=profile / "work", env=environment(profile, provider), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
    async def exchange() -> tuple[bytes, bytes]:
        assert process.stdin is not None
        process.stdin.write(prompt.encode())
        await process.stdin.drain()
        process.stdin.close()
        out, err = await asyncio.gather(bounded_read(process.stdout), bounded_read(process.stderr))
        await process.wait()
        return out, err
    try:
        out, _err = await asyncio.wait_for(exchange(), 180)
        if process.returncode:
            if provider == "claude":
                try:
                    failure = json.loads(out)
                except ValueError:
                    failure = {}
                if failure.get("api_error_status") == 429:
                    raise AccountCliRateLimited("Claude is signed in, but the provider returned 429. Check the account usage limit and retry after it resets")
            raise AccountCliError("The provider could not answer. Complete sign-in in its window, check your plan limits, then retry")
        return parse_output(provider, out.decode("utf-8", errors="replace"))
    except BaseException:
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
        raise


def parse_output(provider: str, text: str) -> dict[str, Any]:
    content: Any = ""
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if provider == "codex":
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                content = event["item"].get("text", "")
            if event.get("type") == "turn.completed":
                values = event.get("usage", {})
                usage = {"prompt_tokens": int(values.get("input_tokens", 0)), "completion_tokens": int(values.get("output_tokens", 0))}
    else:
        try:
            result = json.loads(text)
        except ValueError as error:
            raise AccountCliError("The official provider returned an unreadable response; update its application and retry") from error
        if not isinstance(result, dict) or result.get("is_error") or result.get("error"):
            raise AccountCliError("The provider rejected the request. Check sign-in and plan availability")
        content = result.get("result", result.get("response", result.get("content", "")))
        values = result.get("usage", {})
        usage = {"prompt_tokens": int(values.get("input_tokens", 0)), "completion_tokens": int(values.get("output_tokens", 0))}
        if provider == "gemini":
            for item in result.get("stats", {}).get("models", {}).values():
                tokens = item.get("tokens", {})
                usage["prompt_tokens"] += int(tokens.get("prompt", tokens.get("input", 0)))
                usage["completion_tokens"] += int(tokens.get("candidates", 0))
    if not isinstance(content, str) or not content.strip():
        raise AccountCliError("The official provider did not return a final answer")
    return {"content": content, "usage": usage}


def alias(provider: str, model: str = "default") -> str:
    return f"{ALIAS_PREFIX}{provider}:{model}"


def alias_provider(model: str) -> str | None:
    return next((key for key in PROVIDERS if model.startswith(f"{ALIAS_PREFIX}{key}:")), None)


def alias_model(model: str, provider: str) -> str:
    if alias_provider(model) != provider:
        raise AccountCliError("This model does not belong to the selected account")
    name = model.partition(":")[2]
    if not name or len(name) > 120:
        raise AccountCliError("Invalid account model")
    return name


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["login"])
    parser.add_argument("provider", choices=list(PROVIDERS))
    parser.add_argument("profile", type=Path)
    parser.add_argument("--tools-dir", type=str)
    args = parser.parse_args()
    os.environ["NEXUS_ACCOUNT_CLI_DIR"] = str(args.profile.parents[2])
    if args.tools_dir:
        os.environ["NEXUS_ACCOUNT_TOOLS_DIR"] = args.tools_dir
    prepare(args.profile, args.provider)
    print(f"Alba Agent — {PROVIDERS[args.provider]['name']}\nComplete sign-in with the provider, then return to Alba Agent and check the connection.\n", flush=True)
    result = subprocess.run(command(args.provider, "login"), cwd=args.profile / "work", env=environment(args.profile, args.provider), check=False)
    if result.returncode:
        print("Sign-in did not complete. Return to Alba Agent and try again.")
    elif args.provider == "gemini":
        print("If you signed in successfully, close this session with /quit and return to Alba Agent.")
    sys.exit(result.returncode)
