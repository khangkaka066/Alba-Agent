"""Compile validated workflow graphs into resumable native Flow subclasses."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from dataclasses import asdict
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from crewai.flow.flow import Flow, and_, listen, or_, router, start
from pydantic import BaseModel, Field

from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.store import CheckpointStore
from checkpoints.failure import describe_failure
from crews.tracking import AgentTracker, track_agents
from hooks.claims import claim_material, claimed_files
from crews.builder import CrewBuilder
from flows.state import WorkflowState
from hooks.validator import LifecycleHookEngine
from team_evolution.dynamic_spawner import DynamicSpawner
from nexus_core_schema.artifacts import artifact_directory, artifact_file
from nexus_core_schema.models import (
    ApprovalGateNodeSpec,
    NexusGenSandboxNodeSpec,
    CrewNodeSpec,
    RAGNodeSpec,
    RouterNodeSpec,
    RuntimeEventType,
    WorkflowSpec,
    KnowledgeCapsuleSpec,
    PropagationScope,
    WorkflowEdgeSpec,
)
from nexus_model_gateway.router import BudgetExceeded
from learning_transfer.distiller import DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller


def public_error(error: BaseException) -> str:
    """Return a user-safe failure reason; unexpected errors stay in the worker log."""
    if isinstance(error, (ValueError, LookupError, BudgetExceeded)):
        return str(error)[:300]
    return "The run failed unexpectedly. See the worker log for details."

MAX_SANDBOX_INPUT_PATH_LENGTH = 200
MAX_SANDBOX_INPUT_PATH_DEPTH = 8


def sandbox_input_path_error(name: str) -> str | None:
    """Why `name` cannot be a sandbox input path, or None. Folders are allowed; leaving the working directory is not."""
    if not name or len(name) > MAX_SANDBOX_INPUT_PATH_LENGTH or "\x00" in name or "\\" in name:
        return "Sandbox input paths must be non-empty relative paths without backslashes"
    parts = name.split("/")
    if name.startswith("/") or len(parts) > MAX_SANDBOX_INPUT_PATH_DEPTH or any(part in ("", ".", "..") for part in parts):
        return "Sandbox input paths must stay inside the working directory (no absolute paths, '.', '..' or empty folders)"
    return None


def mount_node_artifacts(state: WorkflowState, sources: list[Any], input_files: dict[str, bytes]) -> list[str]:
    """Copy the delivered files that earlier nodes declared into the sandbox's input files, within its 1 MiB limit.

    A file the run already supplies under the same name is left alone, and a file that is not there (the node did not
    deliver it) is skipped; the node's own contract check reports missing deliverables, this one never invents them.
    """
    directory = artifact_directory(state.tenant_id, state.workspace_id, state.run_id)
    budget = 1_048_576 - sum(len(content) for content in input_files.values())
    mounted: list[str] = []
    for source in sources:
        for path in source.declared_artifact_paths():
            if path in input_files:
                continue
            try:
                candidate = artifact_file(directory, path)
            except ValueError:
                continue
            if not candidate.is_file() or candidate.is_symlink():
                continue
            content = candidate.read_bytes()
            if len(content) > budget:
                continue
            input_files[path] = content
            budget -= len(content)
            mounted.append(path)
    return mounted


MAX_UNDECLARED_FILES = 20
MAX_UNDECLARED_BYTES = 25_000_000

def mount_upstream(state: WorkflowState, input_files: dict[str, bytes]) -> list[dict[str, Any]]:
    """Put the files an earlier team handed over into the sandbox, smallest first, within the sandbox's input limit.
    Larger files (a video, say) are still described to the agents but stay out of the sandbox."""
    folder = artifact_directory(state.tenant_id, state.workspace_id, state.run_id) / ".upstream"
    budget = 1_048_576 - sum(len(content) for content in input_files.values())
    described: list[dict[str, Any]] = []
    upload_budget = 50_000_000
    for entry in sorted(state.upstream_artifacts, key=lambda item: int(item.get("size_bytes", 0))):
        name = str(entry.get("name", ""))
        path = folder / name
        size = int(entry.get("size_bytes", 0))
        uploaded = bool(entry.get("source_upload_id"))
        mounted = bool(name) and name not in {".", ".."} and "/" not in name and "\\" not in name and path.is_file() and not path.is_symlink() and 0 <= size <= (upload_budget if uploaded else budget)
        if mounted:
            input_files[f"upstream/{name}"] = path.read_bytes()
            if uploaded:
                upload_budget -= size
            else:
                budget -= size
        described.append({"name": name, "mounted_path": f"upstream/{name}" if mounted else None, "size_bytes": size,
                          "mime_type": entry.get("mime_type"), "from_task": entry.get("source_run_id")})
    return described



class PauseRequested(Exception):
    """A workflow is durably paused at an approval gate."""


class _FlowWorkflowState(WorkflowState):
    """NexusAI's Flow constructor requires an empty state before applying inputs."""

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID = Field(default_factory=uuid4)


RAGHandler = Callable[[RAGNodeSpec, WorkflowState], Awaitable[dict[str, Any]]]
UsageHandler = Callable[[WorkflowState, str, str, int, int, float], Awaitable[None]]
ModelResolver = Callable[[UUID, UUID, str], Awaitable[Any | None]]
CapsuleHandler = Callable[[KnowledgeCapsuleSpec], Awaitable[None]]
LearningContextHandler = Callable[[WorkflowState, CrewNodeSpec], Awaitable[dict[str, str]]]
LearningOutcomeHandler = Callable[[WorkflowState, CrewNodeSpec, bool, int, int], Awaitable[None]]
ConsensusHandler = Callable[[WorkflowState, Any], Awaitable[dict[str, Any]]]
RequiredToolRunner = Callable[[str, dict[str, Any]], Awaitable[Any]]
SandboxFileReader = Callable[[UUID, UUID, UUID, str], Awaitable[bytes]]
CONTEXT_CHARACTER_LIMIT = 24_000


def json_safe(value: Any) -> Any:
    """Convert tuples, UUIDs and other runtime values into the JSON types crew inputs accept."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _context_text(value: Any, limit: int = CONTEXT_CHARACTER_LIMIT) -> str:
    text = json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "… [truncated; full results are in the run checkpoint]"


def _loop_region(spec: WorkflowSpec, target: str, router_id: str) -> list[str]:
    """Nodes to re-execute when ``router_id`` loops back to ``target``: the target and everything between it
    and the router, in topological order of the forward graph."""
    forward = [edge for edge in spec.edges if not edge.loop_back]
    outgoing: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    incoming: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    for edge in forward:
        outgoing[edge.source].append(edge.target)
        incoming[edge.target].append(edge.source)

    def closure(seed: str, links: dict[str, list[str]]) -> set[str]:
        seen = {seed}
        stack = [seed]
        while stack:
            for nxt in links[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    region = (closure(target, outgoing) & closure(router_id, incoming)) - {router_id}
    order = _topological_order(spec)
    return [node_id for node_id in order if node_id in region]


def _topological_order(spec: WorkflowSpec) -> list[str]:
    indegree = {node.id: 0 for node in spec.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        if not edge.loop_back:
            outgoing[edge.source].append(edge.target)
            indegree[edge.target] += 1
    ready = [node.id for node in spec.nodes if indegree[node.id] == 0]
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    return order


def _read_path(state: WorkflowState, path: str) -> Any:
    current: Any = {"input": state.input_data, **state.node_outputs}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _choose_route(node: RouterNodeSpec, state: WorkflowState) -> str:
    for route in node.routes:
        actual = _read_path(state, route.field_path)
        expected = route.value
        comparisons = {
            "eq": actual == expected,
            "ne": actual != expected,
            "exists": actual is not None,
        }
        if route.operator in comparisons:
            matched = comparisons[route.operator]
        elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            matched = {
                "gt": actual > expected,
                "gte": actual >= expected,
                "lt": actual < expected,
                "lte": actual <= expected,
            }[route.operator]
        else:
            matched = False
        if matched:
            return route.name
    return node.default_route


class CompiledWorkflow:
    def __init__(
        self,
        spec: WorkflowSpec,
        run_id: UUID,
        input_data: dict[str, Any],
        flow_class: type[Flow[WorkflowState]],
        checkpoints: CheckpointStore,
        emitter: RuntimeEventEmitter,
    ) -> None:
        self.spec = spec
        self.run_id = run_id
        self.input_data = input_data
        self.flow_class = flow_class
        self._checkpoints = checkpoints
        self._emitter = emitter

    def _upstream(self) -> list[dict[str, Any]]:
        handed_over = self.input_data.get("upstream_artifacts", [])
        return [dict(item) for item in handed_over if isinstance(item, dict)] if isinstance(handed_over, list) else []

    async def _execute(self, state: WorkflowState) -> WorkflowState:
        flow = self.flow_class(**state.model_dump(mode="python"))
        try:
            await flow.kickoff_async()
        except PauseRequested:
            return WorkflowState.model_validate(flow.state)
        except Exception as exc:
            node_id, node_label = getattr(exc, "nexus_node", (None, None))
            failure = describe_failure(exc, node_id=node_id, node_label=node_label, agent=getattr(exc, "nexus_agent", None))
            flow.state.status = "failed"
            flow.state.active_node_id = None
            await self._checkpoints.save(flow.state)
            await self._checkpoints.record_failure(flow.state, failure)
            where = f"{node_label}: " if node_label else ""
            await self._emitter.emit(
                RuntimeEventType.RUN_FAILED,
                {"error_type": failure["error_type"], "message": f"{where}{failure['error_message']}", "failure": failure},
            )
            raise
        flow.state.status = "completed"
        flow.state.active_node_id = None
        await self._checkpoints.save(flow.state)
        await self._emitter.emit(
            RuntimeEventType.RUN_COMPLETED,
            {
                "completed_nodes": flow.state.completed_nodes, "node_outputs": flow.state.node_outputs,
                "verification": "unverified" if flow.state.unverified_nodes else "verified",
                "unverified_nodes": flow.state.unverified_nodes,
            },
        )
        return WorkflowState.model_validate(flow.state)

    async def run(self) -> WorkflowState:
        state = WorkflowState(
            id=self.run_id,
            run_id=self.run_id,
            workflow_id=self.spec.id,
            tenant_id=self.spec.tenant_id,
            workspace_id=self.spec.workspace_id,
            input_data=self.input_data,
            upstream_artifacts=self._upstream(),
        )
        await self._checkpoints.create_run(state)
        return await self._execute(state)

    async def run_precreated(self) -> WorkflowState:
        """Execute a run already queued durably by the control plane."""
        state = WorkflowState(
            id=self.run_id,
            run_id=self.run_id,
            workflow_id=self.spec.id,
            tenant_id=self.spec.tenant_id,
            workspace_id=self.spec.workspace_id,
            input_data=self.input_data,
            upstream_artifacts=self._upstream(),
            status="running",
        )
        await self._checkpoints.save(state)
        return await self._execute(state)

    async def resume(self) -> WorkflowState:
        state = await self._checkpoints.load(
            self.spec.tenant_id, self.spec.workspace_id, self.run_id
        )
        if state.workflow_id != self.spec.id or state.status != "paused":
            raise ValueError("Run is not a paused instance of this workflow")
        if state.pending_approval_id is None:
            raise ValueError("Paused run has no approval request")
        decision = await self._checkpoints.approval_status(
            state.tenant_id, state.workspace_id, state.pending_approval_id
        )
        if decision == "pending":
            raise PauseRequested("Approval is still pending")
        if decision == "denied":
            state.status = "failed"
            await self._checkpoints.save(state)
            await self._emitter.emit(RuntimeEventType.RUN_FAILED, {"error_type": "ApprovalDenied"})
            return state
        if state.pending_boundary is not None:
            state.node_outputs[f"boundary:{state.sequence}"] = {
                "action": state.pending_boundary["description"], "decision": decision,
            }
            state.pending_boundary = None
            state.pending_approval_id = None
            await self._checkpoints.save(state)
        state.status = "running"
        return await self._execute(state)

    async def resume_execution(self) -> WorkflowState:
        """Replay from the last durable node checkpoint after worker loss."""
        state = await self._checkpoints.load(
            self.spec.tenant_id, self.spec.workspace_id, self.run_id,
        )
        if state.workflow_id != self.spec.id or state.status != "running":
            raise ValueError("Run has no recoverable execution checkpoint")
        return await self._execute(state)


class FlowCompiler:
    def __init__(
        self,
        checkpoints: CheckpointStore,
        emitter: RuntimeEventEmitter,
        sandbox_runner: NexusGenSandboxRunner,
        crew_builder: CrewBuilder | None = None,
        rag_handler: RAGHandler | None = None,
        usage_handler: UsageHandler | None = None,
        model_resolver: ModelResolver | None = None,
        capsule_handler: CapsuleHandler | None = None,
        learning_context_handler: LearningContextHandler | None = None,
        learning_outcome_handler: LearningOutcomeHandler | None = None,
        consensus_handler: ConsensusHandler | None = None,
        required_tool_runner: RequiredToolRunner | None = None,
        sandbox_file_reader: SandboxFileReader | None = None,
        dynamic_spawner: DynamicSpawner | None = None,
    ) -> None:
        self._checkpoints = checkpoints
        self._emitter = emitter
        self._sandbox_runner = sandbox_runner
        self._crew_builder = crew_builder
        self._rag_handler = rag_handler
        self._usage_handler = usage_handler
        self._model_resolver = model_resolver
        self._capsule_handler = capsule_handler
        self._distiller = EpisodicKnowledgeDistiller()
        self._learning_context_handler = learning_context_handler
        self._learning_outcome_handler = learning_outcome_handler
        self._consensus_handler = consensus_handler
        self._required_tool_runner = required_tool_runner
        self._sandbox_file_reader = sandbox_file_reader
        self._dynamic_spawner = dynamic_spawner

    @staticmethod
    def validate(spec: WorkflowSpec) -> WorkflowSpec:
        """Check structural Flow constraints without requiring runtime services.

        The forward graph must be acyclic. Router loop-back edges are an explicit loop contract: they must
        point at an ancestor of the router, and the region they re-run cannot contain an approval gate.
        """
        nodes = {node.id: node for node in spec.nodes}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        for edge in spec.edges:
            if not edge.loop_back:
                outgoing[edge.source].append(edge.target)
        start_ids = [node.id for node in spec.nodes if node.kind == "start"]
        if len(start_ids) != 1:
            raise ValueError("Workflow requires exactly one start node")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Workflow cycles require an explicit loop contract")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in outgoing[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(start_ids[0])
        if visited != nodes.keys():
            raise ValueError("Every workflow node must be reachable from start")
        for edge in spec.edges:
            if not edge.loop_back:
                continue
            region = _loop_region(spec, edge.target, edge.source)
            if edge.target not in region:
                raise ValueError("A loop-back edge must return to an ancestor of its router")
            if any(isinstance(nodes[node_id], ApprovalGateNodeSpec) for node_id in region):
                raise ValueError("A loop-back region cannot contain an approval gate")
        return spec

    async def _export_undeclared(
        self, state: WorkflowState, input_files: dict[str, bytes], produced: tuple[str, ...], prefix: str = "",
    ) -> list[str]:
        """Copy files an agent wrote without a declared contract into the run's artifact directory."""
        assert self._sandbox_file_reader is not None
        directory = artifact_directory(state.tenant_id, state.workspace_id, state.run_id)
        delivered: list[str] = []
        for raw in produced:
            name = raw[2:] if raw.startswith("./") else raw
            if len(delivered) >= MAX_UNDECLARED_FILES or name == "workspace_manifest.json" or "__pycache__" in name.split("/"):
                continue
            try:
                target = artifact_file(directory, prefix + name)
                content = await self._sandbox_file_reader(state.tenant_id, state.workspace_id, state.run_id, name)
            except FileNotFoundError as error:
                # The sandbox reported this file, so failing to read it loses a result. Completing without it would
                # tell the user the work is done and hand back nothing.
                raise RuntimeError(f"Sandbox produced {name} but it could not be exported") from error
            except ValueError:
                continue
            if not content or len(content) > MAX_UNDECLARED_BYTES or input_files.get(name) == content:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            delivered.append(prefix + name)
        return delivered

    def compile(
        self, spec: WorkflowSpec, run_id: UUID, input_data: dict[str, Any] | None = None
    ) -> CompiledWorkflow:
        spec = self.validate(spec)
        if (spec.tenant_id, spec.workspace_id, run_id) != (
            self._emitter.tenant_id, self._emitter.workspace_id, self._emitter.run_id
        ):
            raise ValueError("Workflow scope does not match runtime emitter")
        compile_inputs = dict(input_data or {})
        overrides = compile_inputs.pop("_nexus_node_overrides", {})
        if overrides:
            if not isinstance(overrides, dict):
                raise ValueError("Replay node overrides must be an object")
            updated_nodes: list[Any] = []
            for original in spec.nodes:
                override = overrides.get(original.id)
                if override is None:
                    updated_nodes.append(original)
                    continue
                if not isinstance(override, dict) or set(override) - {"prompt", "model", "temperature"}:
                    raise ValueError("Unsupported replay node override")
                if isinstance(original, CrewNodeSpec):
                    agents = tuple(agent.model_copy(update={
                        **({"model": override["model"]} if "model" in override else {}),
                        **({"temperature": override["temperature"]} if "temperature" in override else {}),
                    }) for agent in original.agents)
                    tasks = tuple(task.model_copy(update={"description": override["prompt"]}) if "prompt" in override and index == 0 else task
                                  for index, task in enumerate(original.tasks))
                    original = original.model_copy(update={"agents": agents, "tasks": tasks})
                elif isinstance(original, NexusGenSandboxNodeSpec):
                    original = original.model_copy(update={
                        **({"coder_model": override["model"], "reviewer_model": override["model"]} if "model" in override else {}),
                        **({"coder_instructions": override["prompt"]} if "prompt" in override else {}),
                    })
                else:
                    raise ValueError("Node does not support prompt/model replay overrides")
                updated_nodes.append(original)
            spec = spec.model_copy(update={"nodes": tuple(updated_nodes)})
        nodes = {node.id: node for node in spec.nodes}
        outgoing: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
        incoming: dict[str, list[WorkflowEdgeSpec]] = {node.id: [] for node in spec.nodes}
        loop_edges: dict[tuple[str, str], list[str]] = {}
        for edge in spec.edges:
            if edge.loop_back:
                loop_edges.setdefault((edge.source, str(edge.route)), []).append(edge.target)
                continue
            outgoing[edge.source].append(edge.target)
            incoming[edge.target].append(edge)
        start_id = next(node.id for node in spec.nodes if node.kind == "start")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Workflow cycles require an explicit loop contract")
            if node_id in visited:
                return
            visiting.add(node_id)
            for child in outgoing[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(start_id)
        if visited != nodes.keys():
            raise ValueError("Every workflow node must be reachable from start")
        if any(isinstance(node, CrewNodeSpec) for node in spec.nodes) and self._crew_builder is None:
            raise ValueError("Crew nodes require an approved crew builder")
        if any(isinstance(node, RAGNodeSpec) for node in spec.nodes) and self._rag_handler is None:
            raise ValueError("Knowledge nodes require an approved retrieval handler")
        name_by_id = {node.id: f"node_{index}" for index, node in enumerate(spec.nodes)}
        lock = asyncio.Lock()
        hook_engine = LifecycleHookEngine(spec.modes.path_rules)
        node_order = _topological_order(spec)
        ownership = {
            node.id: node.declared_artifact_paths()
            for node in spec.nodes if isinstance(node, (CrewNodeSpec, NexusGenSandboxNodeSpec))
        }
        visual_required = any(getattr(node, "requires_visual_evidence", False) for node in spec.nodes)

        trackers: dict[str, AgentTracker] = {}
        # With an artifact gate a missing file sends the work back for rework; without one nothing would, so a team that
        # did not deliver what it declared (or claimed) fails here instead of finishing as if it had.
        gated = any(isinstance(item, RouterNodeSpec) and item.artifact_gate for item in spec.nodes)

        async def apply_contract(state: WorkflowState, node: Any, output: dict[str, Any], paths: tuple[str, ...],
                                 task_outputs: dict[str, dict[str, Any]], sources: dict[str, bytes] | None,
                                 documents: dict[str, dict[str, Any]] | None = None) -> None:
            if not paths:
                return
            directory = artifact_directory(state.tenant_id, state.workspace_id, state.run_id)
            task_paths = {path: task.id for task in getattr(node, "tasks", ()) for path in task.expected_artifact_paths}
            checks: list[dict[str, Any]] = []
            merged: dict[str, list[str]] = {"verified": [], "recovered": [], "missing": [], "invalid": [], "warnings": []}
            for path in paths:
                structured = (documents or {}).get(path) or task_outputs.get(task_paths.get(path, ""), output)
                report = hook_engine.after_node(directory, node.id, (path,), structured, sources).as_output()
                checks.append(report)
                for key in merged:
                    merged[key].extend(report[key])
            contract: dict[str, Any] = {**merged, "passed": not merged["missing"] and not merged["invalid"]}
            output["artifact_contract"] = contract
            if contract["warnings"]:
                await self._emitter.emit(RuntimeEventType.TOOL_INVOKED, {
                    "tool": "artifact_contract", "audit": "warning", "node_id": node.id,
                    "recovered": contract["recovered"], "missing": contract["missing"], "invalid": contract["invalid"],
                    "warnings": contract["warnings"][:20],
                }, node.id)
            if not gated and not contract["passed"]:
                problems = [f"{path} (missing)" for path in merged["missing"]] + [f"{path} (invalid)" for path in merged["invalid"]]
                raise ValueError(f"The team did not deliver what it reported: {', '.join(problems[:5])}")

        def gate_verdict(state: WorkflowState, node: RouterNodeSpec) -> dict[str, Any]:
            rework_targets = [target for (source, _route), targets in loop_edges.items() if source == node.id for target in targets]
            verdict = hook_engine.evaluate_gate(
                artifact_directory(state.tenant_id, state.workspace_id, state.run_id),
                state.node_outputs, ownership, node_order, rework_targets, visual_required,
            )
            return verdict.as_output()

        live: dict[str, WorkflowState] = {}

        async def run_dynamic(sub: CrewNodeSpec | NexusGenSandboxNodeSpec, task: str) -> dict[str, Any]:
            """Execute a team member spawned mid-run by a director, with the same contract checks as any node."""
            state = live["state"]
            output: dict[str, Any]
            if isinstance(sub, CrewNodeSpec):
                assert self._crew_builder is not None
                overrides: dict[str, Any] = {}
                if self._model_resolver is not None:
                    for agent_spec in sub.agents:
                        resolved = await self._model_resolver(state.tenant_id, state.workspace_id, agent_spec.model)
                        if resolved is None:
                            raise ValueError("Spawned specialist model requires managed credit or a workspace provider key")
                        overrides[agent_spec.model] = resolved
                paths = list(sub.declared_artifact_paths())
                block = hook_engine.rules.instruction_block(paths)
                built = self._crew_builder.build(sub, overrides, {sub.tasks[0].id: block} if block else {})
                crew_result = await built.crew.kickoff_async(inputs={
                    "input": _context_text(state.input_data),
                    "nodes": _context_text(state.node_outputs),
                })
                structured = getattr(crew_result, "pydantic", None)
                if not isinstance(structured, BaseModel):
                    raise ValueError("Spawned specialist did not return its required structured output")
                output = structured.model_dump(mode="json")
                await apply_contract(state, sub, output, tuple(paths), {}, None)
                usage = getattr(crew_result, "token_usage", None)
                if usage is not None and self._usage_handler is not None:
                    prompt_tokens, completion_tokens = int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)
                    if prompt_tokens or completion_tokens:
                        await self._usage_handler(state, sub.agents[0].id, sub.agents[0].model, prompt_tokens, completion_tokens, 0.0)
            else:
                payload = json.dumps({
                    "request": state.input_data.get("task", ""), "instructions": sub.coder_instructions,
                    "completed_node_outputs": json_safe(state.node_outputs),
                    "deliverable_contract": hook_engine.rules.instruction_block(sub.expected_artifact_paths),
                }, ensure_ascii=False, separators=(",", ":"), default=str)
                result = await self._sandbox_runner.run(payload, sub, self._emitter)
                output = json_safe(asdict(result))
                if result.exit_code != 0:
                    raise RuntimeError("Spawned sandbox subtask failed verification")
                exported: dict[str, bytes] = {}
                if self._sandbox_file_reader is not None:
                    for path in sub.expected_artifact_paths:
                        try:
                            exported[path] = await self._sandbox_file_reader(state.tenant_id, state.workspace_id, state.run_id, path)
                        except (FileNotFoundError, ValueError):
                            continue
                await apply_contract(state, sub, output, sub.expected_artifact_paths, {}, exported)
            contract = output.get("artifact_contract", {})
            await self._emitter.emit(RuntimeEventType.TOOL_INVOKED, {
                "tool": "dynamic_team_mutator", "node_id": sub.id, "label": sub.label, "task": task[:300],
                "verified": contract.get("verified", []), "recovered": contract.get("recovered", []),
                "missing": contract.get("missing", []),
            }, sub.id)
            return {"summary": str(output.get("summary", ""))[:2000], "artifact_contract": contract, "exit_code": output.get("exit_code", 0)}

        if self._dynamic_spawner is not None:
            self._dynamic_spawner.bind(spec, run_dynamic)

        async def execute_node(flow: Flow[WorkflowState], node: Any) -> Any:
            async with lock:
                state = flow.state
                if node.id in state.completed_nodes:
                    output = state.node_outputs[node.id]
                    if isinstance(node, RouterNodeSpec):
                        return f"{name_by_id[node.id]}:{output['route']}"
                    return output
                try:
                    return await run_node(flow, node)
                except PauseRequested:
                    raise
                except Exception as error:
                    setattr(error, "nexus_node", (node.id, getattr(node, "label", None) or node.id))  # lets the run record say where it stopped
                    tracker = trackers.get(node.id)
                    agent_name = tracker.culprit if tracker is not None else ("Coder + Reviewer" if isinstance(node, NexusGenSandboxNodeSpec) else None)
                    if agent_name and getattr(error, "nexus_agent", None) is None:
                        setattr(error, "nexus_agent", agent_name)
                    raise

        async def run_node(flow: Flow[WorkflowState], node: Any) -> Any:
            state = flow.state
            state.status = "running"
            state.active_node_id = node.id
            await self._emitter.emit(
                RuntimeEventType.FLOW_STATE_CHANGED,
                {"status": "running", "node_id": node.id},
                node.id,
            )
            if getattr(node, "consensus_config", None) is not None and node.consensus_config.enabled:
                if self._consensus_handler is None:
                    raise ValueError("Consensus mode requires an approved model gateway handler")
                consensus_output = await self._consensus_handler(state, node)
                output = consensus_output
                if bool(consensus_output.get("approval_required")):
                    state.node_outputs[node.id] = output
                    state.completed_nodes.append(node.id)
                    state.pending_boundary = {"description": f"Consensus arbitration: {consensus_output.get('dissent_report', '')[:500]}", "node_id": node.id}
                    approval_id = await self._checkpoints.request_approval(
                        state, node.id, "Consensus confidence is below the configured threshold",
                        "builder", 86_400,
                    )
                    await self._emitter.emit(RuntimeEventType.APPROVAL_REQUIRED, {
                        "approval_id": str(approval_id), "kind": "consensus_arbitration",
                        "drafts": consensus_output.get("drafts", []),
                        "dissent_report": consensus_output.get("dissent_report", ""),
                        "consensus_confidence": consensus_output.get("consensus_confidence", 0.0),
                    }, node.id)
                    raise PauseRequested()
            elif node.kind == "start":
                output = state.input_data
            elif isinstance(node, CrewNodeSpec):
                assert self._crew_builder is not None
                crew_started = time.monotonic()
                build_node = node
                if self._learning_context_handler is not None:
                    injected = await self._learning_context_handler(state, node)
                    if injected:
                        agents = tuple(agent.model_copy(update={
                            "backstory": f"{agent.backstory}\n\nVerified workspace learning (scoped and sanitized):\n{injected[agent.id]}"
                        }) if agent.id in injected else agent for agent in node.agents)
                        build_node = node.model_copy(update={"agents": agents})
                model_overrides: dict[str, Any] = {}
                if self._model_resolver is not None:
                    for agent_spec in build_node.agents:
                        resolved = await self._model_resolver(state.tenant_id, state.workspace_id, agent_spec.model)
                        if resolved is None:
                            raise ValueError("Crew model requires managed credit or a workspace provider key")
                        model_overrides[agent_spec.model] = resolved
                preambles: dict[str, str] = {}
                for task_index, task_spec in enumerate(build_node.tasks):
                    task_paths = list(task_spec.expected_artifact_paths)
                    if task_index == len(build_node.tasks) - 1:
                        task_paths.extend(build_node.expected_artifact_paths)
                    block = hook_engine.rules.instruction_block(task_paths)
                    if block:
                        preambles[task_spec.id] = block + "\nReturn the run-relative path of every file you wrote."
                built = self._crew_builder.build(build_node, model_overrides, preambles)
                trackers[node.id] = track_agents(built.crew)
                spawned_before = len(self._dynamic_spawner.records) if self._dynamic_spawner is not None else 0
                if self._dynamic_spawner is not None:
                    live["state"] = state
                    self._dynamic_spawner.activate(node.id)
                try:
                    crew_result = await built.crew.kickoff_async(inputs={
                        "input": _context_text(state.input_data),
                        "nodes": _context_text({key: value for key, value in state.node_outputs.items() if key != node.id}),
                    })
                except Exception:
                    if self._learning_outcome_handler is not None:
                        await self._learning_outcome_handler(state, node, False, 0, int((time.monotonic() - crew_started) * 1000))
                    raise
                finally:
                    if self._dynamic_spawner is not None:
                        self._dynamic_spawner.deactivate()
                structured = getattr(crew_result, "pydantic", None)
                if not isinstance(structured, BaseModel):
                    raise ValueError("Crew did not return its required Pydantic output")
                output = structured.model_dump(mode="json")
                if self._dynamic_spawner is not None and len(self._dynamic_spawner.records) > spawned_before:
                    output["dynamic_team"] = [record.as_output() for record in self._dynamic_spawner.records[spawned_before:]]
                task_outputs: dict[str, dict[str, Any]] = {}
                for task_spec, task_result in zip(node.tasks, getattr(crew_result, "tasks_output", None) or ()):
                    task_model = getattr(task_result, "pydantic", None)
                    if isinstance(task_model, BaseModel):
                        task_outputs[task_spec.id] = task_model.model_dump(mode="json")
                if len(task_outputs) > 1:
                    output["task_outputs"] = task_outputs
                if "artifact_filename" in output or "report_filename" in output:
                    directory = artifact_directory(state.tenant_id, state.workspace_id, state.run_id)
                    recovered_artifacts = False
                    def existing_file(field: str) -> str | None:
                        filename = output.get(field)
                        if not isinstance(filename, str):
                            return None
                        try:
                            path = artifact_file(directory, filename)
                        except ValueError:
                            return None
                        return filename if path.is_file() else None
                    file_fields = tuple(field for field in ("artifact_filename", "report_filename") if field in output)
                    if any(not existing_file(field) for field in file_fields):
                        if len(file_fields) != 2 or self._required_tool_runner is None or not any(
                            "media_generation" in agent.tool_ids and "report_exporter" in agent.tool_ids
                            for agent in node.agents
                        ):
                            missing = ", ".join(field for field in file_fields if not existing_file(field))
                            raise ValueError(f"Crew did not produce required artifacts: {missing}")
                        recovered_artifacts = True
                        instruction = node.tasks[-1].description
                        kind = "video" if "kind=video" in instruction else "audio" if "kind=audio" in instruction else "image"
                        file_match = __import__("re").search(r"\bfilename=([A-Za-z0-9_-]{1,80})\b", instruction)
                        stem = file_match.group(1) if file_match else "generated_media"
                        if not existing_file("artifact_filename"):
                            media_result = await self._required_tool_runner("media_generation", {
                                "kind": kind, "prompt": str(state.input_data.get("task") or instruction), "filename": stem,
                            })
                            if not isinstance(media_result, dict) or not isinstance(media_result.get("artifact"), str):
                                raise ValueError("Media tool did not return an artifact filename")
                            output["artifact_filename"] = media_result["artifact"]
                        if not existing_file("report_filename"):
                            report_result = await self._required_tool_runner("report_exporter", {
                                "format": "markdown", "filename": f"{stem}_script",
                                "content": (
                                    f"# Production report\n\n## Request\n\n{state.input_data.get('task', '')}\n\n"
                                    f"## Delivered media\n\n{output.get('artifact_filename', '')}\n\n"
                                    "The media tool returned this file, and the workflow verified it exists in the run artifact directory.\n"
                                ),
                            })
                            if not isinstance(report_result, dict) or not isinstance(report_result.get("artifact"), str):
                                raise ValueError("Report tool did not return an artifact filename")
                            output["report_filename"] = report_result["artifact"]
                    for field in file_fields:
                        if not existing_file(field):
                            raise ValueError(f"Crew claimed a missing {field} artifact")
                    if recovered_artifacts and "summary" in output:
                        output["summary"] = (
                            "Runtime generated and verified deliverables: "
                            f"{output['artifact_filename']}, {output['report_filename']}"
                        )
                declared = node.declared_artifact_paths()
                claims = [name for name in claimed_files((*task_outputs.values(), output)) if name not in declared]
                material = claim_material(task_outputs, output) if claims else {}
                crew_exports: dict[str, bytes] = {}
                if self._sandbox_file_reader is not None:
                    for path in (*declared, *claims):
                        try:
                            if not artifact_file(artifact_directory(state.tenant_id, state.workspace_id, state.run_id), path).is_file():
                                crew_exports[path] = await self._sandbox_file_reader(state.tenant_id, state.workspace_id, state.run_id, path)
                        except (FileNotFoundError, ValueError):
                            continue
                await apply_contract(state, node, output, (*declared, *claims), task_outputs, crew_exports, {name: material for name in claims} if material else None)
                confidence = output.get("evaluation_confidence", output.get("confidence", 0.0))
                if self._capsule_handler is not None and isinstance(confidence, (int, float)) and confidence >= 0.9:
                    capsule = self._distiller.distill(DistillationCandidate(
                        tenant_id=state.tenant_id, workspace_id=state.workspace_id,
                        source_agent_id=node.agents[0].id, source_role=node.agents[0].role,
                        trigger=DistillationTrigger.HIGH_CONFIDENCE_TASK,
                        heuristic=str(output.get("lesson", output.get("summary", structured))),
                        preconditions=str(output.get("preconditions", node.tasks[0].description)),
                        domain_tags=tuple(output.get("domain_tags", ())), confidence=float(confidence),
                        workflow_id=state.workflow_id, crew_id=node.id,
                        propagation_scope=PropagationScope.CREW_LOCAL,
                    ))
                    if capsule is not None:
                        await self._capsule_handler(capsule)
                usage = getattr(crew_result, "token_usage", None) or getattr(built.crew, "usage_metrics", None)
                crew_tokens = 0
                if usage is not None and self._usage_handler is not None:
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                    crew_tokens = prompt_tokens + completion_tokens
                    if prompt_tokens or completion_tokens:
                        await self._usage_handler(
                            state, node.agents[0].id, node.agents[0].model, prompt_tokens, completion_tokens, 0.0,
                        )
                if self._learning_outcome_handler is not None:
                    await self._learning_outcome_handler(state, node, True, crew_tokens, int((time.monotonic() - crew_started) * 1000))
            elif isinstance(node, NexusGenSandboxNodeSpec):
                input_files: dict[str, bytes] = {}
                supplied_files = state.input_data.get("sandbox_files", {})
                if supplied_files is not None:
                    if not isinstance(supplied_files, dict):
                        raise ValueError("Sandbox files must be a filename-to-text object")
                    for supplied_name, supplied_content in supplied_files.items():
                        if not isinstance(supplied_name, str) or not isinstance(supplied_content, str):
                            raise ValueError("Sandbox files must contain text file values")
                        path_error = sandbox_input_path_error(supplied_name)
                        if path_error:
                            raise ValueError(path_error)
                        input_files[supplied_name] = supplied_content.encode("utf-8")
                uploaded_name = state.input_data.get("filename")
                if not isinstance(uploaded_name, str) or uploaded_name != uploaded_name.rsplit("/", 1)[-1] or uploaded_name != uploaded_name.rsplit("\\", 1)[-1]:
                    uploaded_name = "dataset.csv"
                dataset_filename = ""
                dataset = state.input_data.get("dataset")
                if isinstance(dataset, str) and dataset:
                    dataset_filename = uploaded_name if uploaded_name.lower().endswith(".csv") else "dataset.csv"
                    input_files[dataset_filename] = dataset.encode("utf-8")
                encoded_workbook = state.input_data.get("dataset_base64")
                if isinstance(encoded_workbook, str) and encoded_workbook:
                    workbook_name = uploaded_name if uploaded_name.lower().endswith(".xlsx") else "dataset.xlsx"
                    dataset_filename = workbook_name
                    try:
                        input_files[workbook_name] = base64.b64decode(encoded_workbook, validate=True)
                    except ValueError as error:
                        raise ValueError("XLSX workflow input is not valid base64") from error
                if sum(len(content) for content in input_files.values()) > 1_048_576:
                    raise ValueError("Sandbox file inputs exceed the 1 MiB workflow run limit")
                mounted_from_nodes = mount_node_artifacts(state, [nodes[source_id] for source_id in node.mount_artifacts_from], input_files)
                mounted_upstream = mount_upstream(state, input_files)
                task_input = dict(state.input_data)
                task_input.pop("sandbox_files", None)
                task_input.pop("upstream_artifacts", None)
                if "dataset" in task_input:
                    task_input["dataset"] = {"mounted_path": dataset_filename, "format": "csv"}
                if "dataset_base64" in task_input:
                    task_input["dataset_base64"] = {"mounted_path": dataset_filename, "format": "xlsx"}
                sandbox_task: dict[str, Any] = {
                    "request": state.input_data.get("task", ""),
                    "instructions": node.coder_instructions,
                    "input_data": task_input,
                    "completed_node_outputs": json_safe(state.node_outputs),
                    "mounted_files": sorted(input_files),
                }
                if state.upstream_artifacts:
                    sandbox_task["upstream_artifacts"] = mounted_upstream
                if mounted_from_nodes:
                    sandbox_task["files_from_earlier_nodes"] = mounted_from_nodes
                contract_block = hook_engine.rules.instruction_block(node.expected_artifact_paths)
                if contract_block:
                    sandbox_task["deliverable_contract"] = contract_block + "\nWrite each file relative to the working directory, creating folders as needed."
                task = json.dumps(sandbox_task, ensure_ascii=False, separators=(",", ":"), default=str)
                sandbox_result = (
                    await self._sandbox_runner.run(task, node, self._emitter, input_files=input_files)
                    if input_files else await self._sandbox_runner.run(task, node, self._emitter)
                )
                output = json_safe(asdict(sandbox_result))
                delivered_unverified = False
                handed_on = False
                output["verified"] = sandbox_result.exit_code == 0
                if sandbox_result.exit_code != 0:
                    reason = sandbox_result.verification.get("reason")
                    if node.on_failure == "continue":
                        # A router after this node decides what happens next; the attempt's files are evidence, not a deliverable.
                        handed_on = True
                        output["failure_reason"] = str(reason) if reason else "verification did not pass"
                    else:
                        if not (sandbox_result.verification.get("status") == "unverified" and node.on_unverified == "deliver_labeled"):
                            raise RuntimeError(f"Sandbox verification failed: {reason}" if reason else "Sandbox verification failed")
                        delivered_unverified = True
                        state.unverified_nodes.append(node.id)
                        if self._sandbox_file_reader is not None:
                            # Kept apart from verified artifacts so nobody mistakes a candidate for a proven result.
                            output["unverified_files"] = await self._export_undeclared(state, input_files, sandbox_result.artifacts, "unverified/")
                delivered_unverified = delivered_unverified or handed_on
                if node.expected_artifact_paths and not delivered_unverified:
                    exported: dict[str, bytes] = {}
                    produced = {name.lstrip("./") for name in sandbox_result.artifacts}
                    if self._sandbox_file_reader is not None:
                        for path in node.expected_artifact_paths:
                            if path in produced:
                                try:
                                    exported[path] = await self._sandbox_file_reader(state.tenant_id, state.workspace_id, state.run_id, path)
                                except (FileNotFoundError, ValueError):
                                    continue
                    await apply_contract(state, node, output, node.expected_artifact_paths, {}, exported)
                elif self._sandbox_file_reader is not None and not delivered_unverified:
                    # No declared deliverables: still hand back what the sandbox actually wrote, so a plain
                    # request produces files the user can open. Unchanged mounted inputs are not deliverables.
                    delivered = await self._export_undeclared(state, input_files, sandbox_result.artifacts)
                    if delivered:
                        output["exported_files"] = delivered
                attempts = sandbox_result.metrics.get("attempts", 0)
                debug_turns = max(0, int(attempts) - 1) if isinstance(attempts, (int, float)) else 0
                if self._capsule_handler is not None and debug_turns >= 2 and not delivered_unverified:
                    capsule = self._distiller.distill(DistillationCandidate(
                        tenant_id=state.tenant_id, workspace_id=state.workspace_id,
                        source_agent_id=f"{node.id}_coder", source_role="coding and verification",
                        trigger=DistillationTrigger.DEBUG_RECOVERY,
                        heuristic=sandbox_result.summary,
                        preconditions=str(state.input_data.get("task", node.coder_instructions or "Python coding or verification")),
                        domain_tags=("python", "sandbox", "code-verification"), debug_turns=debug_turns,
                        workflow_id=state.workflow_id, crew_id=node.id,
                        propagation_scope=PropagationScope.WORKFLOW_SCOPED,
                    ))
                    if capsule is not None:
                        await self._capsule_handler(capsule)
                if self._usage_handler is not None:
                    for agent_name, model, prefix in (
                        ("nexusgen_coder", node.coder_model, "coder"),
                        ("nexusgen_reviewer", node.reviewer_model, "reviewer"),
                    ):
                        prompt_tokens = int(sandbox_result.metrics.get(f"{prefix}_prompt_tokens", 0))
                        completion_tokens = int(sandbox_result.metrics.get(f"{prefix}_completion_tokens", 0))
                        if prompt_tokens or completion_tokens:
                            await self._usage_handler(
                                state, agent_name, model, prompt_tokens, completion_tokens,
                                float(sandbox_result.metrics.get("sandbox_seconds", 0.0)) if prefix == "coder" else 0.0,
                            )
            elif isinstance(node, ApprovalGateNodeSpec):
                if state.pending_approval_id is None:
                    approval_id = await self._checkpoints.request_approval(
                        state, node.id, node.action_description,
                        node.required_role, node.timeout_seconds,
                    )
                    await self._emitter.emit(
                        RuntimeEventType.APPROVAL_REQUIRED,
                        {"approval_id": str(approval_id), "action": node.action_description, "required_role": node.required_role},
                        node.id,
                    )
                    raise PauseRequested()
                decision = await self._checkpoints.approval_status(
                    state.tenant_id, state.workspace_id, state.pending_approval_id
                )
                if decision not in ("allowed_once", "always_allowed"):
                    raise PauseRequested()
                output = {"approval_id": str(state.pending_approval_id), "decision": decision}
                state.pending_approval_id = None
                await self._emitter.emit(RuntimeEventType.APPROVAL_RESOLVED, output, node.id)
            elif isinstance(node, RouterNodeSpec):
                output = await run_router(flow, node)
            elif isinstance(node, RAGNodeSpec):
                assert self._rag_handler is not None
                output = await self._rag_handler(node, state)
            else:
                raise TypeError("Unsupported workflow node")
            state.node_outputs[node.id] = output
            state.completed_nodes.append(node.id)
            state.active_node_id = None
            await self._checkpoints.save(state)
            await self._emitter.emit(
                RuntimeEventType.FLOW_STATE_CHANGED,
                {"status": "completed", "node_id": node.id},
                node.id,
            )
            if isinstance(node, RouterNodeSpec):
                return f"{name_by_id[node.id]}:{output['route']}"
            return output

        async def run_router(flow: Flow[WorkflowState], node: RouterNodeSpec) -> dict[str, Any]:
            """Choose a route; loop-back routes re-run the responsible region within the loop budget."""
            state = flow.state
            loops_key = f"{node.id}__loops"
            while True:
                if node.artifact_gate:
                    state.node_outputs[node.gate_key()] = gate_verdict(state, node)
                route = _choose_route(node, state)
                targets = loop_edges.get((node.id, route), [])
                if not targets:
                    return {"route": route, "rework_loops": int(state.node_outputs.get(loops_key, 0))}
                iteration = int(state.node_outputs.get(loops_key, 0))
                verdict = state.node_outputs.get(node.gate_key(), {}) if node.artifact_gate else {}
                if iteration >= node.max_loop_iterations:
                    reasons = "; ".join(str(reason) for reason in verdict.get("reasons", ())[:5]) if isinstance(verdict, dict) else ""
                    raise ValueError(
                        f"{node.label} still routes to '{route}' after {iteration} rework loop(s)"
                        + (f": {reasons}" if reasons else "")
                    )
                state.node_outputs[loops_key] = iteration + 1
                state.node_outputs["rework_feedback"] = json_safe({
                    "router": node.id, "route": route, "iteration": iteration + 1,
                    "reasons": verdict.get("reasons", []) if isinstance(verdict, dict) else [],
                    "missing": verdict.get("missing", []) if isinstance(verdict, dict) else [],
                    "instruction": "Fix the listed problems. Write every required file at its exact path before finishing.",
                })
                await self._emitter.emit(RuntimeEventType.FLOW_STATE_CHANGED, {
                    "status": "rework", "node_id": node.id, "route": route, "targets": targets, "iteration": iteration + 1,
                }, node.id)
                region: list[str] = []
                for target in targets:
                    region.extend(node_id for node_id in _loop_region(spec, target, node.id) if node_id not in region)
                ordered = [node_id for node_id in node_order if node_id in region]
                for node_id in ordered:
                    if node_id in state.completed_nodes:
                        state.completed_nodes.remove(node_id)
                    state.node_outputs.pop(node_id, None)
                await self._checkpoints.save(state)
                for node_id in ordered:
                    await run_node(flow, nodes[node_id])

        attributes: dict[str, Any] = {"__module__": __name__}
        for node in spec.nodes:
            name = name_by_id[node.id]

            async def method(flow: Flow[WorkflowState], _previous: Any = None, *, _node: Any = node) -> Any:
                return await execute_node(flow, _node)

            method.__name__ = name
            decorated: Any
            if node.id == start_id:
                decorated = start()(method)
            else:
                triggers: list[str] = []
                for edge in incoming[node.id]:
                    source = nodes[edge.source]
                    if isinstance(source, RouterNodeSpec):
                        triggers.append(f"{name_by_id[source.id]}:{edge.route}")
                    else:
                        triggers.append(name_by_id[source.id])
                if not triggers:
                    raise ValueError("Non-start node has no incoming edge")
                join_all = getattr(node, "join", "any") == "all" and not any(isinstance(nodes[edge.source], RouterNodeSpec) for edge in incoming[node.id])
                condition = triggers[0] if len(triggers) == 1 else (and_(*triggers) if join_all else or_(*triggers))
                decorated = router(condition)(method) if isinstance(node, RouterNodeSpec) else listen(condition)(method)
            attributes[name] = decorated
        flow_class = type(f"NexusFlow_{run_id.hex}", (Flow[_FlowWorkflowState],), attributes)
        return CompiledWorkflow(
            spec, run_id, compile_inputs, flow_class,
            self._checkpoints, self._emitter,
        )
