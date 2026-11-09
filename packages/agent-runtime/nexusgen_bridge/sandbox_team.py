"""Two-agent coding review with isolated execution and live run events."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.models import ChatCompletionClient
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from callbacks.event_bus import RuntimeEventEmitter
from agent_skills import SkillLoader
from nexus_computer_sandbox import ComputerSandboxSupervisor, DockerSandboxSupervisor, SandboxExecution
from nexus_core_schema.models import NexusGenSandboxNodeSpec, RuntimeEventType
from verification import (
    Evidence, Status, VerificationReport, build_probe, build_self_test_probe, decide, parse_probe_output, parse_self_test_output,
    protected_test_hashes,
)

# Pattern matching test filenames — kept in sync with verification.probe._TEST_NAME.
_TEST_NAME_RE = re.compile(r"^(test_[A-Za-z0-9_]*|[A-Za-z0-9_]*_test)\.py$")
from .patcher import compile_patch_script, is_patch_text, parse_patch_blocks


_FAILURE_LINE_RE = re.compile(
    r"^(?:"
    r"FAIL:|FAILED|ERROR:|AssertionError:|AssertionError |"
    r"NameError:|TypeError:|ValueError:|SyntaxError:|"
    r"IndexError:|KeyError:|AttributeError:|ImportError:|"
    r"ModuleNotFoundError:|FileNotFoundError:|"
    r"assert |FAILURES"
    r")",
)


def compact_log(text: str, max_chars: int = 2500) -> str:
    """Trim excessive execution logs while preserving crucial tracebacks and failure lines.

    Guarantees:
    - Never exceeds max_chars and never exceeds 16,384 characters hard ceiling.
    - Deduplicates failure lines in O(n) time using a set.
    - Caps failure lines to a strict character budget within max_chars.
    """
    text = text.strip()
    # Absolute ceiling: never allow output larger than 16,384 chars or max_chars
    ceiling = min(max(max_chars, 500), 16_384)
    if len(text) <= ceiling:
        return text

    # Extract failure lines with O(1) deduplication
    seen: set[str] = set()
    unique_failures: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _FAILURE_LINE_RE.match(stripped):
            if stripped not in seen:
                seen.add(stripped)
                unique_failures.append(stripped)

    # Allocate strict character budgets
    head_len = min(400, ceiling // 5)
    tail_len = min(600, ceiling // 4)
    # Banner and overhead budget (~120 chars)
    overhead = 120
    max_failure_budget = max(0, ceiling - head_len - tail_len - overhead)

    kept_failures: list[str] = []
    curr_failure_len = 0
    overflow_count = 0
    for idx, f in enumerate(unique_failures):
        line_len = len(f) + 1  # include newline
        reserve = 45  # reserve room for "... and N other unique failure line(s)" note
        if curr_failure_len + line_len + reserve <= max_failure_budget:
            kept_failures.append(f)
            curr_failure_len += line_len
        else:
            overflow_count = len(unique_failures) - idx
            break

    if overflow_count > 0:
        kept_failures.append(f"... and {overflow_count} other unique failure line(s)")

    failures_block = "\n".join(kept_failures)
    head = text[:head_len]
    tail = text[-tail_len:]
    trimmed = len(text) - head_len - tail_len

    parts = [head]
    if failures_block:
        parts.append(f"\n\n[... {trimmed} chars truncated — unique failures below ...]\n")
        parts.append(failures_block)
        parts.append(f"\n\n{tail}")
    else:
        parts.append(f"\n\n[... {trimmed} chars truncated ...]\n\n{tail}")

    result = "".join(parts)
    if len(result) > ceiling:
        return result[:ceiling]
    return result


def extract_failure_summary(stdout: str, stderr: str) -> str:
    """Extract a concise single-line failure reason from execution output."""
    combined = (stderr + "\n" + stdout).strip()
    for line in reversed(combined.splitlines()):
        line = line.strip()
        if any(line.startswith(err) for err in (
            "AssertionError:", "NameError:", "TypeError:", "ValueError:", "SyntaxError:",
            "IndexError:", "KeyError:", "AttributeError:", "FAILED", "PatchError:"
        )):
            return line[:160]
    lines = [l.strip() for l in combined.splitlines() if l.strip()]
    return lines[-1][:160] if lines else "Non-zero exit code"

def require_declared_files(report: VerificationReport, declared: tuple[str, ...], present: tuple[str, ...]) -> VerificationReport:
    """A node that declares its deliverables is not verified until those files exist.

    The run's working directory is shared by every node, so tests and files left by an earlier node can make a probe pass
    before this node has written anything; the files this node promised are the only proof that it did its own work.
    """
    if report.status is not Status.VERIFIED or not declared:
        return report
    have = {name.lstrip("./") for name in present}
    missing = [path for path in declared if path not in have]
    if not missing:
        return report
    return VerificationReport(
        Status.UNVERIFIED, report.level,
        f"the checks pass but this node has not written its declared files yet: {', '.join(missing[:5])}; "
        "write them here (files left by other nodes do not count)", report.evidence)


# Probe scripts take attempt numbers far above any coder attempt so the two never collide in one run directory.
_PROBE_ATTEMPT_BASE = 1000


@dataclass(frozen=True)
class SandboxResult:
    summary: str
    artifacts: tuple[str, ...]
    exit_code: int
    metrics: dict[str, int | float]
    verification: dict[str, object] = field(default_factory=dict)


class NexusGenSandboxRunner:
    def __init__(
        self,
        supervisor: ComputerSandboxSupervisor | DockerSandboxSupervisor,
        model_client_factory: Callable[..., ChatCompletionClient | Awaitable[ChatCompletionClient]],
        before_run: Callable[[UUID, UUID, int], Awaitable[None]] | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._model_client_factory = model_client_factory
        self._before_run = before_run
        # Sandbox nodes running at once in this process. Each holds a container, so an unbounded burst of runs
        # starves the Docker daemon and turns finished work into infrastructure failures.
        self._slots = asyncio.Semaphore(max(1, int(os.environ.get("NEXUS_SANDBOX_MAX_CONCURRENT", "4"))))
        self._skill_loader = SkillLoader()
        self._skill_resolver: Callable[[UUID, UUID, tuple[str, ...]], Awaitable[dict[str, str]]] | None = None
        self._tool_resolver: Callable[[UUID, UUID, UUID, tuple[str, ...]], Awaitable[list[Any]]] | None = None

    def set_skill_resolver(self, resolver: Callable[[UUID, UUID, tuple[str, ...]], Awaitable[dict[str, str]]]) -> None:
        self._skill_resolver = resolver

    def set_tool_resolver(self, resolver: Callable[[UUID, UUID, UUID, tuple[str, ...]], Awaitable[list[Any]]]) -> None:
        self._tool_resolver = resolver

    async def _model_client(self, model: str, emitter: RuntimeEventEmitter) -> ChatCompletionClient:
        factory = self._model_client_factory
        try:
            inspect.signature(factory).bind(model, emitter.tenant_id, emitter.workspace_id)
        except (TypeError, ValueError):
            result = factory(model)
        else:
            result = factory(model, emitter.tenant_id, emitter.workspace_id)
        if inspect.isawaitable(result):
            return await result
        return result

    async def run(
        self,
        task: str,
        spec: NexusGenSandboxNodeSpec,
        emitter: RuntimeEventEmitter,
        input_files: dict[str, bytes] | None = None,
    ) -> SandboxResult:
        """Run one sandbox node: wait for a free slot, and give the container back as soon as the node is done."""
        if not task.strip():
            raise ValueError("Sandbox task cannot be empty")
        persistent = self._supervisor if isinstance(self._supervisor, ComputerSandboxSupervisor) else None
        async with self._slots:
            if persistent is not None:
                await persistent.acquire_run(emitter.run_id)
            try:
                return await self._run_node(task, spec, emitter, input_files)
            finally:
                if persistent is not None:
                    try:
                        await persistent.release_run(emitter.tenant_id, emitter.workspace_id, emitter.run_id)
                    except Exception:
                        logging.getLogger("nexus.sandbox").exception("Sandbox computer could not be released", extra={"run_id": str(emitter.run_id)})

    async def _run_node(
        self,
        task: str,
        spec: NexusGenSandboxNodeSpec,
        emitter: RuntimeEventEmitter,
        input_files: dict[str, bytes] | None = None,
    ) -> SandboxResult:
        if not task.strip():
            raise ValueError("Sandbox task cannot be empty")
        matched_skills = self._skill_loader.match(task)
        selected_ids = tuple(dict.fromkeys((*spec.skill_ids, *(skill.slug for skill in matched_skills))))
        overrides = await self._skill_resolver(emitter.tenant_id, emitter.workspace_id, selected_ids) if self._skill_resolver is not None else {}
        unknown = set(selected_ids) - self._skill_loader._skills.keys() - overrides.keys()
        if unknown:
            raise LookupError(f"Assigned skills are not available: {', '.join(sorted(unknown))}")
        skill_parts = [
            f"## Skill: {slug}\n\n{overrides[slug] if slug in overrides else self._skill_loader.get(slug).body}"
            for slug in selected_ids
        ]
        skill_instructions = "\n\n".join(skill_parts)
        if self._before_run is not None:
            # Reserve one attempt, not the worst case of every round: reserving timeout x rounds consumed a whole
            # FREE month in a single node and made any second sandbox node fail. Real usage is recorded afterwards.
            await self._before_run(emitter.tenant_id, emitter.workspace_id, spec.timeout_seconds)
        coder_client = await self._model_client(spec.coder_model, emitter)
        reviewer_client = await self._model_client(spec.reviewer_model, emitter)
        run_started = time.monotonic()
        attempts = 0
        attempts_history: list[dict[str, Any]] = []
        initial_files_staged = False
        script_label = f"{re.sub(r'[^A-Za-z0-9_]', '_', spec.id)[:36]}_{uuid4().hex[:8]}"
        last_execution: SandboxExecution | None = None
        reviewer_summary = ""
        approved = False
        usage_by_agent = {"coder": [0, 0], "reviewer": [0, 0]}
        protected_tests = protected_test_hashes(input_files or {})
        probes = 0
        last_evidence: Evidence | None = None
        probe_seconds = 0.0
        # A verified result is final (the reviewer cannot change it), so the next reviewer turn would only cost latency.
        verified_stop = ExternalTermination()

        async def probe_evidence() -> Evidence | None:
            """Run a probe the coder cannot edit; this, not the reviewer, is the evidence.

            Staged tests are run as they are. With none staged, the coder's own tests face the self-test gates.
            """
            nonlocal probes, probe_seconds
            probes += 1
            source, nonce = build_probe(protected_tests) if protected_tests else build_self_test_probe(input_files or {})

            async def probe_sink(stream: str, content: str) -> None:
                await emitter.emit(
                    RuntimeEventType.SANDBOX_TERMINAL_OUTPUT,
                    {"attempt": attempts, "stream": f"probe_{stream}", "content": content},
                    spec.id,
                )

            started = time.monotonic()
            execution = await self._supervisor.run_python(
                emitter.tenant_id, emitter.workspace_id, emitter.run_id, source, "true",
                _PROBE_ATTEMPT_BASE + probes, spec.timeout_seconds, probe_sink,
                script_label=script_label,
            )
            probe_seconds += time.monotonic() - started
            parse = parse_probe_output if protected_tests else parse_self_test_output
            return parse(execution.stdout, nonce)

        async def execute_python(code: str) -> str:
            """Execute Python in the approved isolated run computer and return verification output."""
            nonlocal attempts, last_execution, last_evidence, initial_files_staged
            attempts += 1
            last_evidence = None
            if attempts > spec.max_rounds:
                raise ValueError("Maximum sandbox attempts exceeded")
            await emitter.emit(
                RuntimeEventType.NEXUSGEN_CODE_GENERATED,
                {"attempt": attempts, "code": code},
                spec.id,
            )
            await emitter.emit(
                RuntimeEventType.TOOL_INVOKED,
                {"tool": "nexus_code_execution", "attempt": attempts},
                spec.id,
            )

            # Check if code is a SEARCH/REPLACE diff patch
            if is_patch_text(code):
                try:
                    blocks = parse_patch_blocks(code)
                    code_to_run = compile_patch_script(blocks)
                except ValueError as err:
                    attempts_history.append({
                        "attempt": attempts,
                        "exit_code": 1,
                        "status": "FAILED",
                        "error_summary": f"PatchError: {err}",
                    })
                    return json.dumps({
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": f"PatchError: {err}",
                        "artifacts": last_execution.artifacts if last_execution else (),
                        "attempts_history": attempts_history,
                    })
            else:
                # Fast syntax validation before container execution
                try:
                    ast.parse(code)
                except SyntaxError as err:
                    err_msg = f"SyntaxError: {err.msg} at line {err.lineno}: {err.text or ''}".strip()
                    attempts_history.append({
                        "attempt": attempts,
                        "exit_code": 1,
                        "status": "FAILED",
                        "error_summary": err_msg,
                    })
                    return json.dumps({
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": err_msg,
                        "artifacts": last_execution.artifacts if last_execution else (),
                        "attempts_history": attempts_history,
                        "syntax_error": True,
                    })
                code_to_run = code

            async def output_sink(stream: str, content: str) -> None:
                await emitter.emit(
                    RuntimeEventType.SANDBOX_TERMINAL_OUTPUT,
                    {"attempt": attempts, "stream": stream, "content": content},
                    spec.id,
                )

            # Only re-stage protected tests if initial_files have already been
            # successfully written to the sandbox filesystem on a prior run_python call.
            # If attempt 1 exited early (syntax error or patch parse error), initial files
            # were never written yet, so they must be staged now.
            staged_files = input_files
            if initial_files_staged and input_files:
                staged_files = {
                    name: data
                    for name, data in input_files.items()
                    if _TEST_NAME_RE.match(name.rsplit("/", 1)[-1])
                }

            last_execution = await self._supervisor.run_python(
                emitter.tenant_id,
                emitter.workspace_id,
                emitter.run_id,
                code_to_run,
                spec.verification_command,
                attempts,
                spec.timeout_seconds,
                output_sink,
                input_files=staged_files,
                script_label=script_label,
            )
            initial_files_staged = True
            verdict = None
            if last_execution.exit_code == 0:
                last_evidence = await probe_evidence()
                verdict = require_declared_files(
                    decide(last_evidence, execution_ok=True, min_added_tests=spec.min_added_tests if protected_tests else 0),
                    spec.expected_artifact_paths, last_execution.artifacts)
                if verdict.status is Status.VERIFIED:
                    verified_stop.set()

            is_verified = verdict is not None and verdict.status is Status.VERIFIED
            status = "VERIFIED" if is_verified else ("PASSED" if last_execution.exit_code == 0 else "FAILED")
            err_summary = None if last_execution.exit_code == 0 else extract_failure_summary(last_execution.stdout, last_execution.stderr)
            attempts_history.append({
                "attempt": attempts,
                "exit_code": last_execution.exit_code,
                "status": status,
                "error_summary": err_summary,
            })

            result: dict[str, object] = {
                "exit_code": last_execution.exit_code,
                "stdout": compact_log(last_execution.stdout)[-4000:],
                "stderr": (last_execution.error_digest or {}).get("root_cause_line", compact_log(last_execution.stderr)[-2000:]),
                "error_digest": last_execution.error_digest,
                "snapshot_id": last_execution.snapshot_id,
                "artifacts": last_execution.artifacts,
                "attempts_history": attempts_history,
            }
            if verdict is not None:
                result["verification"] = verdict.as_dict()
            return json.dumps(result)

        native_tools = await self._tool_resolver(emitter.tenant_id, emitter.workspace_id, emitter.run_id, spec.tool_ids) if spec.tool_ids and self._tool_resolver is not None else []
        if spec.tool_ids and self._tool_resolver is None:
            raise LookupError("Built-in tools are unavailable for this sandbox run")
        coder = AssistantAgent(
            name="coder",
            model_client=coder_client,
            tools=[execute_python, *native_tools],
            system_message=(
                "Write Python to solve the task. Call execute_python for each attempt. "
                "Read the execution result and repair failures. Never claim completion without a zero exit code. "
                "When the result has a verification block, a trusted probe judged your work: keep repairing until its status is verified. "
                "The deliverable list limits published artifacts, not working test files: keep test_*.py in the workspace root and publish only the requested deliverables. "
                + (
                    "For web UI checks, serve files with start_background_process and use browser_automation on its loopback URL. "
                    "Use the configured isolated browser; do not launch host Chrome, use a host browser profile, or install another browser stack. "
                    if "browser_automation" in spec.tool_ids else ""
                )
                +
                "To repair existing files, you can output SEARCH/REPLACE diff blocks to execute_python instead of rewriting full files:\n"
                "<<<<<<< SEARCH: filename.py\nold lines\n=======\nnew lines\n>>>>>>> REPLACE\n"
                "You can batch multiple SEARCH/REPLACE blocks for different files in a single turn.\n"
                + (
                    "The task ships tests; never edit them. They cover only part of the behaviour: the task text and the "
                    "docstrings state more, and a grader checks all of it. Before your first execute_python call, list every "
                    "behavioural clause of the task text and of the docstrings you read (each rule, each error case, each "
                    "'also applies to' sentence) and make sure the code handles each one, including inputs the shipped "
                    "tests never use."
                    + (
                        f" Then write at least {spec.min_added_tests} tests of your own in a new test_*.py file, one per clause the shipped "
                        "tests never exercise, derived from the task text and not from your implementation; the result is not verified until they pass."
                        if spec.min_added_tests else ""
                    )
                    if protected_tests else
                    "No tests ship with this task, so write your own as a unittest file named test_<module>.py in the working "
                    "directory, derived from the task text and not from your implementation: at least 4 cases including edge "
                    "cases. They must fail on the starting code and catch deliberate mutations of your code; the block reports "
                    "how many mutants they caught."
                )
                + ("\n\nAssigned skill instructions:\n" + skill_instructions if skill_instructions else "")
            ),
            max_tool_iterations=1,
        )
        reviewer = AssistantAgent(
            name="reviewer",
            model_client=reviewer_client,
            system_message=(
                "Review the code and execution result. Reply APPROVED with a short summary only "
                "after verification exits zero, a verification block (if present) says verified, and every file named in the "
                "task's deliverable contract exists. "
                "Otherwise describe the repair needed in 1-2 concise sentences without repeating code or logs."
                + (f"\n\nReview focus:\n{spec.reviewer_instructions}" if spec.reviewer_instructions else "")
            ),
        )
        team = RoundRobinGroupChat(
            [coder, reviewer],
            termination_condition=TextMentionTermination("APPROVED", sources=["reviewer"]) | verified_stop,
            max_turns=spec.max_rounds * 2,
        )
        try:
            async for item in team.run_stream(task=task):
                if isinstance(item, TaskResult):
                    continue
                source = getattr(item, "source", "")
                content = getattr(item, "content", None)
                usage = getattr(item, "models_usage", None)
                if usage is not None and source in usage_by_agent:
                    usage_by_agent[source][0] += int(usage.prompt_tokens)
                    usage_by_agent[source][1] += int(usage.completion_tokens)
                if source in ("coder", "reviewer") and isinstance(content, str):
                    await emitter.emit(
                        RuntimeEventType.CREW_AGENT_THOUGHT,
                        {"agent": source, "content": content},
                        spec.id,
                    )
                    if source == "reviewer":
                        reviewer_summary = content
                        approved = "APPROVED" in content
        finally:
            await coder_client.close()
            if reviewer_client is not coder_client:
                await reviewer_client.close()
        execution_ok = last_execution is not None and last_execution.exit_code == 0
        report = require_declared_files(
            decide(last_evidence, execution_ok=execution_ok, min_added_tests=spec.min_added_tests if protected_tests else 0),
            spec.expected_artifact_paths, last_execution.artifacts if last_execution else ())
        # Executed evidence decides. The reviewer's opinion can neither promote a result nor demote a verified one.
        if report.status is Status.VERIFIED:
            exit_code = 0
            summary = reviewer_summary.replace("APPROVED", "").strip() or report.reason
        else:
            exit_code = last_execution.exit_code if last_execution is not None and last_execution.exit_code != 0 else 1
            summary = report.reason
        return SandboxResult(
            summary=summary,
            artifacts=last_execution.artifacts if last_execution else (),
            exit_code=exit_code,
            verification=report.as_dict(),
            metrics={
                "attempts": attempts,
                "prompt_tokens": sum(tokens[0] for tokens in usage_by_agent.values()),
                "completion_tokens": sum(tokens[1] for tokens in usage_by_agent.values()),
                "coder_prompt_tokens": usage_by_agent["coder"][0],
                "coder_completion_tokens": usage_by_agent["coder"][1],
                "reviewer_prompt_tokens": usage_by_agent["reviewer"][0],
                "reviewer_completion_tokens": usage_by_agent["reviewer"][1],
                "sandbox_seconds": last_execution.elapsed_seconds if last_execution else 0.0,
                "probe_seconds": round(probe_seconds, 2),
                "total_seconds": round(time.monotonic() - run_started, 2),
            },
        )


class CodeExecutionInput(BaseModel):
    task: str = Field(min_length=1, description="The coding or data task to solve")


class NexusGenCodeExecutionTool(BaseTool):
    name: str = "nexus_code_execution"
    description: str = "Delegate a Python coding or data task to a reviewed isolated computer"
    args_schema: type[BaseModel] = CodeExecutionInput

    _runner: NexusGenSandboxRunner = PrivateAttr()
    _spec: NexusGenSandboxNodeSpec = PrivateAttr()
    _emitter: RuntimeEventEmitter = PrivateAttr()

    def __init__(
        self,
        runner: NexusGenSandboxRunner,
        spec: NexusGenSandboxNodeSpec,
        emitter: RuntimeEventEmitter,
    ) -> None:
        super().__init__(name="nexus_code_execution", description="Delegate a Python coding or data task to a reviewed isolated computer")
        self._runner = runner
        self._spec = spec
        self._emitter = emitter

    async def _arun(self, task: str) -> str:
        result = await self._runner.run(task, self._spec, self._emitter)
        return json.dumps({
            "summary": result.summary,
            "artifacts": result.artifacts,
            "exit_code": result.exit_code,
            "metrics": result.metrics,
        })

    def _run(self, task: str) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._arun(task))
        raise RuntimeError("Use the async tool method inside a running event loop")
