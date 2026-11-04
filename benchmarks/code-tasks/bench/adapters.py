"""Agent adapters. Each runs ONE task unattended in a workspace and reports what happened.

All systems share the same ShopAIKey endpoint, key and model (see ``Endpoint``), the same prompt wrapper
and the same wall-clock limit. Secrets come from the environment only and are never written to results.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Every tool runs with an empty HOME so the operator's own skills, CLAUDE.md, memory and settings
# (for example ~/.agents/skills, ~/.claude) cannot leak into the measurement.
CLEAN_HOME = "/Users/nguyenvokhang/bench-tools/home-empty"
DSH_BIN = "/Users/nguyenvokhang/bench-tools/dsh/node_modules/.bin/dsh"
DSH_HOME = "/Users/nguyenvokhang/bench-tools/dsh/home"

PROMPT_WRAPPER = """You are working in the current directory, which is a small Python project.

TASK
{task}

RULES
- Change files in this directory only. Run Python or the tests yourself if you need to check your work.
- Use only the Python standard library.
- When you finish, end your final message with exactly one line: `RESULT: DONE` if you believe the task is complete, or `RESULT: BLOCKED` if you could not complete it.
"""


@dataclass(frozen=True)
class Endpoint:
    """The one ShopAIKey configuration all three systems use."""

    openai_base_url: str  # OpenAI-compatible root, e.g. https://api.shopaikey.com/v1
    anthropic_base_url: str  # Anthropic-compatible root used by Claude Code
    api_key: str
    model: str

    @staticmethod
    def from_env() -> "Endpoint":
        def need(name: str) -> str:
            value = os.environ.get(name, "")
            if not value:
                raise SystemExit(f"{name} is not set (put it in your shell or an untracked .env)")
            return value

        return Endpoint(
            openai_base_url=need("BENCH_OPENAI_BASE_URL"),
            anthropic_base_url=need("BENCH_ANTHROPIC_BASE_URL"),
            api_key=need("BENCH_API_KEY"),
            model=need("BENCH_MODEL"),
        )


@dataclass
class AgentOutcome:
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    interventions: int = 0
    timed_out: bool = False
    infra_error: str = ""  # provider/network/auth problem, not the tool's fault; run is retried then excluded
    error: str = ""
    raw: dict[str, object] = field(default_factory=dict)


class Adapter(Protocol):
    name: str

    def run(self, task_prompt: str, workspace: Path, timeout_seconds: int) -> AgentOutcome: ...


def wrapped(task_prompt: str) -> str:
    return PROMPT_WRAPPER.format(task=task_prompt.strip())


_INFRA_MARKERS = ("401", "403", "429", "500", "502", "503", "504", "overloaded", "rate limit", "ECONNRESET",
                  "ETIMEDOUT", "Connection error", "Unable to connect", "timed out")


def looks_like_infra(message: str) -> bool:
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in _INFRA_MARKERS)


class ClaudeCodeAdapter:
    """Claude Code CLI in --bare mode (no CLAUDE.md, hooks or memory from the operator's machine)."""

    name = "claude_code"
    ALLOWED_TOOLS = "Read Edit Write Glob Grep Bash(python3:*) Bash(python:*) Bash(ls:*) Bash(cat:*) Bash(grep:*) Bash(find:*) Bash(head:*) Bash(tail:*) Bash(sed:*) Bash(wc:*) Bash(mkdir:*) Bash(cp:*) Bash(mv:*)"

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    def permission_args(self) -> list[str]:
        """Strict allowlist: anything else is denied and counted as an intervention."""
        return ["--permission-mode", "dontAsk", "--allowedTools", self.ALLOWED_TOOLS]

    def run(self, task_prompt: str, workspace: Path, timeout_seconds: int) -> AgentOutcome:
        env = {
            "PATH": os.environ["PATH"], "HOME": CLEAN_HOME,
            "ANTHROPIC_BASE_URL": self.endpoint.anthropic_base_url,
            "ANTHROPIC_API_KEY": self.endpoint.api_key,
            "ANTHROPIC_MODEL": self.endpoint.model,
            "ANTHROPIC_SMALL_FAST_MODEL": self.endpoint.model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self.endpoint.model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self.endpoint.model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": self.endpoint.model,
            "DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        command = [
            "claude", "--bare", "-p", wrapped(task_prompt), "--output-format", "json",
            "--model", self.endpoint.model, *self.permission_args(), "--no-session-persistence",
        ]
        try:
            proc = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True,
                                  timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return AgentOutcome(timed_out=True, error="wall-clock limit")
        outcome = AgentOutcome(raw={"returncode": proc.returncode, "stderr": proc.stderr[-2000:]})
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            message = (proc.stdout + proc.stderr)[-800:]
            if looks_like_infra(message):
                outcome.infra_error = message
            else:
                outcome.error = message or f"exit {proc.returncode}, no JSON output"
            return outcome
        usage = data.get("usage") or {}
        outcome.final_text = str(data.get("result") or "")
        outcome.input_tokens = int(usage.get("input_tokens") or 0)
        outcome.output_tokens = int(usage.get("output_tokens") or 0)
        outcome.cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
        outcome.cache_write_tokens = int(usage.get("cache_creation_input_tokens") or 0)
        outcome.interventions = len(data.get("permission_denials") or [])
        outcome.raw["num_turns"] = data.get("num_turns")
        if data.get("is_error"):
            if looks_like_infra(outcome.final_text):
                outcome.infra_error = outcome.final_text[-800:]
            else:
                outcome.error = outcome.final_text[-800:]
        return outcome


class ClaudeCodeSandboxAdapter(ClaudeCodeAdapter):
    """Claude Code with its own OS sandbox on and Bash auto-allowed inside it: the counterpart of dsh's workspace-write."""

    name = "claude_code_sbx"

    def permission_args(self) -> list[str]:
        settings = json.dumps({"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True}})
        return ["--permission-mode", "dontAsk", "--settings", settings,
                "--allowedTools", "Read Edit Write Glob Grep Bash"]


class DshAdapter:
    """DeepSeek Harness, headless profile, JSON event stream; ShopAIKey through its llm-pi-ai plugin."""

    name = "dsh"

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    def run(self, task_prompt: str, workspace: Path, timeout_seconds: int) -> AgentOutcome:
        env = {
            "PATH": os.environ["PATH"], "HOME": CLEAN_HOME, "DSH_HOME": DSH_HOME,
            "BENCH_API_KEY": self.endpoint.api_key, "BENCH_OPENAI_BASE_URL": self.endpoint.openai_base_url,
            "DSH_TELEMETRY_OTLP_URL": "http://127.0.0.1:9/v1/logs",  # plugin is also disabled in the profile patch
            "DSH_PERMISSION_MODE": "workspace-write",
        }
        try:
            proc = subprocess.run([DSH_BIN, "--profile", "headless", "--json", wrapped(task_prompt)], cwd=workspace,
                                  env=env, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return AgentOutcome(timed_out=True, error="wall-clock limit")
        outcome = AgentOutcome(raw={"returncode": proc.returncode, "stderr": proc.stderr[-1500:]})
        statuses: dict[str, int] = {}
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "final":
                outcome.final_text = str(event.get("text") or "")
            elif kind == "status" and isinstance(event.get("usage"), dict):
                usage = event["usage"]
                outcome.input_tokens += int(usage.get("inputTokens") or 0)
                outcome.output_tokens += int(usage.get("outputTokens") or 0)
                outcome.cache_read_tokens += int(usage.get("cacheReadTokens") or 0)
            elif kind == "tool_result":
                status = str(event.get("status"))
                statuses[status] = statuses.get(status, 0) + 1
                if status not in {"completed", "failed", "error"}:
                    outcome.interventions += 1  # denied / awaiting approval
        outcome.raw["tool_result_statuses"] = statuses
        if not outcome.final_text:
            message = (proc.stdout[-600:] + proc.stderr[-600:]).replace(self.endpoint.api_key, "REDACTED")
            if looks_like_infra(message):
                outcome.infra_error = message
            else:
                outcome.error = message or f"exit {proc.returncode}, no final event"
        return outcome


TOKEN_REFRESH_SECONDS = 300


class NexusAgentAdapter:
    """NexusAgent control plane over HTTP: generate a minimal team, force one model, run it, copy artifacts back.

    Controlled deviations from "as shipped", so that all three systems use the same model:
    every agent/coder/reviewer model is set to the benchmark model and swarm consensus (which the architect
    enables with a second model family) is switched off. The architect call counts toward wall time and cost.
    Interventions = approval pauses the run hit; each is approved at once, as an attentive human would.
    """

    name = "nexus"
    plain_prompt = False  # nexus_plain: the task text alone, no RESULT-line rules

    def __init__(self, endpoint: Endpoint, api_url: str = "http://127.0.0.1:8000") -> None:
        self.endpoint = endpoint
        self.api_url = api_url.rstrip("/")
        self.model_ref = f"openai/{endpoint.model}"

    def _call(self, method: str, path: str, body: object | None = None, token: str = "", timeout: int = 120) -> object:
        request = urllib.request.Request(
            self.api_url + path, method=method, data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw) if raw else None

    def _new_token(self) -> str:
        return str(self._call("POST", "/api/v1/auth/local-session")["access_token"])  # type: ignore[index]

    def _prompt(self, task_prompt: str) -> str:
        return task_prompt.strip() if self.plain_prompt else wrapped(task_prompt)

    def _pin_model(self, spec: dict[str, object]) -> dict[str, object]:
        for node in spec.get("nodes", []):  # type: ignore[attr-defined]
            if node.get("consensus_config"):
                node["consensus_config"] = {**node["consensus_config"], "enabled": False, "models": [], "arbiter_model": ""}
            for agent in node.get("agents", []) or []:
                agent["model"] = self.model_ref
            for key in ("coder_model", "reviewer_model"):
                if key in node:
                    node[key] = self.model_ref
        return spec

    def run(self, task_prompt: str, workspace: Path, timeout_seconds: int) -> AgentOutcome:
        deadline = time.monotonic() + timeout_seconds
        outcome = AgentOutcome()
        files = {
            path.relative_to(workspace).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(workspace.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        try:
            token = self._new_token()
            token_issued = time.monotonic()
            generated = self._call("POST", "/api/v1/architect/generate-workflow", {
                "user_requirement_prompt": self._prompt(task_prompt), "preferred_model": self.model_ref, "rigor": "minimal",
                "auto_run": False}, token, timeout=min(300, timeout_seconds))
            spec = self._pin_model(generated["workflow_spec"])  # type: ignore[index]
            spec["name"] = f"{str(spec['name'])[:80]} [{uuid.uuid4().hex[:8]}]"
            saved = self._call("POST", "/api/v1/workflows", spec, token)  # type: ignore[index]
            started = self._call("POST", f"/api/v1/workflows/{saved['id']}/runs", {  # type: ignore[index]
                "input_data": {"task": self._prompt(task_prompt), "sandbox_files": files}}, token)
            run_id = started["run_id"]  # type: ignore[index]
            approved: set[str] = set()
            while True:
                if time.monotonic() > deadline:
                    outcome.timed_out, outcome.error = True, "wall-clock limit"
                    return outcome
                time.sleep(4)
                if time.monotonic() - token_issued > TOKEN_REFRESH_SECONDS:  # access tokens expire mid-run on long tasks
                    token, token_issued = self._new_token(), time.monotonic()
                run = self._call("GET", f"/api/v1/runs/{run_id}", token=token)
                pending = run.get("pending_approval_id")  # type: ignore[union-attr]
                if pending and pending not in approved:
                    approved.add(pending)
                    outcome.interventions += 1
                    self._call("POST", f"/api/v1/approvals/{pending}/resolve", {"decision": "allow_once"}, token)
                status = run.get("status")  # type: ignore[union-attr]
                if status in {"completed", "failed", "cancelled"}:
                    break
            token = self._new_token()
            outcome.raw = {"run_id": run_id, "status": status, "failure": run.get("failure"), "approvals": len(approved)}  # type: ignore[union-attr]
            unverified = False
            for artifact in self._call("GET", f"/api/v1/runs/{run_id}/artifacts", token=token) or []:  # type: ignore[union-attr]
                name = artifact.get("filename")
                if not name or name.startswith("."):
                    continue
                # Files NexusAgent itself labels unverified sit under `unverified/`; they are graded like any other
                # output but the run is recorded as completed_unverified and does not count as a claim of success.
                local = name[len("unverified/"):] if name.startswith("unverified/") else name
                unverified = unverified or local != name
                target = (workspace / local).resolve()
                if not local or workspace.resolve() not in target.parents:
                    continue
                request = urllib.request.Request(f"{self.api_url}/api/v1/runs/{run_id}/artifacts/{urllib.parse.quote(name, safe='/')}",
                                                 headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(response.read())
            if unverified and status == "completed":
                status = "completed_unverified"
                outcome.raw["status"] = status
            failure = run.get("failure")  # type: ignore[union-attr]
            outcome.final_text = "RESULT: DONE" if status == "completed" else (
                "NexusAgent labelled the result unverified\nRESULT: BLOCKED" if status == "completed_unverified"
                else f"run {status}: {json.dumps(failure)[:300]}\nRESULT: BLOCKED")
        except urllib.error.HTTPError as error:
            message = f"HTTP {error.code}: {error.read().decode()[:300]}"
            # 400/401/403/404/405 mean our own harness is wrong, 429/5xx mean the service is unavailable:
            # neither says anything about answer quality, so the attempt is retried and then excluded.
            harness_or_service = error.code in {400, 401, 403, 404, 405, 409, 429} or error.code >= 500
            outcome.infra_error = message if harness_or_service else ""
            outcome.error = "" if harness_or_service else message
        except (urllib.error.URLError, TimeoutError, KeyError) as error:
            message = f"{type(error).__name__}: {error}"
            outcome.infra_error = message if looks_like_infra(message) or isinstance(error, (urllib.error.URLError, TimeoutError)) else ""
            outcome.error = "" if outcome.infra_error else message
        return outcome


class NexusAgentPlainAdapter(NexusAgentAdapter):
    """Ablation: identical to nexus but the task text is sent unchanged (no RESULT-line instructions)."""

    name = "nexus_plain"
    plain_prompt = True

    def run(self, task_prompt: str, workspace: Path, timeout_seconds: int) -> AgentOutcome:
        outcome = super().run(task_prompt, workspace, timeout_seconds)
        return outcome


def timed(fn):  # type: ignore[no-untyped-def]
    start = time.monotonic()
    result = fn()
    return result, time.monotonic() - start
