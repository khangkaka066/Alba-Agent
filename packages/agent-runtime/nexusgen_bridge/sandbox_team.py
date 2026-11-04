"""Two-agent coding review with isolated execution and live run events."""

from __future__ import annotations

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
    Evidence, Status, build_probe, build_self_test_probe, decide, parse_probe_output, parse_self_test_output,
    protected_test_hashes,
)

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
            nonlocal attempts, last_execution, last_evidence
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

            async def output_sink(stream: str, content: str) -> None:
                await emitter.emit(
                    RuntimeEventType.SANDBOX_TERMINAL_OUTPUT,
                    {"attempt": attempts, "stream": stream, "content": content},
                    spec.id,
                )

            last_execution = await self._supervisor.run_python(
                emitter.tenant_id,
                emitter.workspace_id,
                emitter.run_id,
                code,
                spec.verification_command,
                attempts,
                spec.timeout_seconds,
                output_sink,
                input_files=input_files,
                script_label=script_label,
            )
            result: dict[str, object] = {
                "exit_code": last_execution.exit_code,
                "stdout": last_execution.stdout[-16_384:],
                "stderr": last_execution.stderr[-16_384:],
                "artifacts": last_execution.artifacts,
            }
            if last_execution.exit_code == 0:
                last_evidence = await probe_evidence()
                verdict = decide(last_evidence, execution_ok=True)
                result["verification"] = verdict.as_dict()
                if verdict.status is Status.VERIFIED:
                    verified_stop.set()
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
                + (
                    "The task ships tests; never edit them. They cover only part of the behaviour: the task text and the "
                    "docstrings state more, and a grader checks all of it. Before your first execute_python call, list every "
                    "behavioural clause of the task text and of the docstrings you read (each rule, each error case, each "
                    "'also applies to' sentence) and make sure the code handles each one, including inputs the shipped "
                    "tests never use."
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
                "Otherwise describe the repair needed."
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
        report = decide(last_evidence, execution_ok=execution_ok)
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
