"""Mid-run team adaptation: directors and department leads spawn a specialist or sandbox subtask on demand."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from nexus_core_schema.models import NexusGenSandboxNodeSpec, CrewNodeSpec, WorkflowSpec

from .domains import discover_skills, discover_tools
from .models import SpawnSpecialist
from .topology_mutator import MutationError, TeamTopologyMutator, _deliverable_schema, _schema_name

TOOL_ID = "dynamic_team_mutator"
MAX_SPAWNS_PER_RUN = 3
SANDBOX_VERIFY_DEFAULT = "python -c \"print('ok')\""

SubtaskExecutor = Callable[[CrewNodeSpec | NexusGenSandboxNodeSpec, str], Awaitable[dict[str, Any]]]
PersistHandler = Callable[["SpawnRecord", WorkflowSpec], Awaitable[dict[str, Any]]]


class DynamicSpawnRequest(BaseModel):
    """What a director asks for when the team lacks a capability it needs to finish or fix the product."""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(default="specialist", description="'specialist' for a new Tier-3 agent, 'sandbox' for a code or compilation subtask")
    role: str = Field(description="Role of the specialist (or a short label for the sandbox subtask)")
    goal: str = Field(description="What this specialist must achieve")
    task: str = Field(description="The concrete job to run right now, including the files to produce")
    expected_artifact_paths: list[str] = Field(default_factory=list, description="Run-relative files the subtask must write, for example design/diagram.md")
    department_node_id: str = Field(default="", description="Department crew node that should own this specialist when persisted; defaults to the caller's node")
    tool_ids: list[str] = Field(default_factory=list)
    persist: bool = Field(default=False, description="Also add the specialist to the permanent workflow as a proposed new team generation")
    rationale: str = Field(default="", description="Why the existing team cannot do this")


@dataclass
class SpawnRecord:
    kind: str
    role: str
    department_node_id: str
    node_id: str
    paths: tuple[str, ...]
    persist: bool
    rationale: str
    result: dict[str, Any] = field(default_factory=dict)
    persisted: dict[str, Any] | None = None

    def as_output(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "role": self.role, "department": self.department_node_id, "node_id": self.node_id,
            "paths": list(self.paths), "persisted": self.persisted, "result": self.result,
        }


class DynamicSpawner:
    """Per-run service behind ``DynamicTeamMutatorTool``. The runtime activates it around every crew node."""

    def __init__(
        self,
        mutator: TeamTopologyMutator,
        available_tools: Collection[str] | None = None,
        available_models: Sequence[str] = (),
        max_spawns: int = MAX_SPAWNS_PER_RUN,
        persist_handler: PersistHandler | None = None,
    ) -> None:
        self._mutator = mutator
        self._tools = available_tools
        self._models = tuple(available_models)
        self._max = max_spawns
        self._persist = persist_handler
        self._executor: SubtaskExecutor | None = None
        self._spec: WorkflowSpec | None = None
        self._current: str | None = None
        self.records: list[SpawnRecord] = []
        self._lock = asyncio.Lock()

    def bind(self, spec: WorkflowSpec, executor: SubtaskExecutor) -> None:
        self._spec, self._executor = spec, executor

    def activate(self, node_id: str) -> None:
        self._current = node_id

    def deactivate(self) -> None:
        self._current = None

    async def spawn(self, request: DynamicSpawnRequest) -> dict[str, Any]:
        if self._executor is None or self._spec is None or self._current is None:
            raise MutationError("Dynamic team mutation is only available while a crew node is running")
        async with self._lock:
            if len(self.records) >= self._max:
                raise MutationError(f"This run already spawned {self._max} on-the-fly team members")
            spec, caller = self._spec, self._current
            nodes = {node.id: node for node in spec.nodes}
            caller_node = nodes.get(caller)
            if not isinstance(caller_node, CrewNodeSpec) or not any(agent.tier in ("director", "lead") for agent in caller_node.agents):
                raise MutationError("Only crews led by a director or department lead may reshape the team")
            department = request.department_node_id or caller
            paths = tuple(dict.fromkeys(request.expected_artifact_paths))
            node: CrewNodeSpec | NexusGenSandboxNodeSpec
            if request.kind == "sandbox":
                node = self._sandbox_node(request, paths)
            elif request.kind == "specialist":
                node = self._specialist_node(request, caller_node, paths)
            else:
                raise MutationError("kind must be 'specialist' or 'sandbox'")
            taken = {path for item in spec.nodes if isinstance(item, (CrewNodeSpec, NexusGenSandboxNodeSpec)) for path in item.declared_artifact_paths()}
            taken |= {path for earlier in self.records for path in earlier.paths}
            if set(paths) & taken:
                raise MutationError(f"Artifact path already owned by the team: {', '.join(sorted(set(paths) & taken))}")
            record = SpawnRecord(request.kind, request.role, department, node.id, paths, request.persist, request.rationale)
            assert self._executor is not None
            record.result = await self._executor(node, request.task)
            if request.persist:
                record.persisted = await self._persist_record(spec, record, request)
            self.records.append(record)
            return record.as_output()

    def _specialist_node(self, request: DynamicSpawnRequest, caller: CrewNodeSpec, paths: tuple[str, ...]) -> CrewNodeSpec:
        text = f"{request.role} {request.goal} {request.task}"
        tools = discover_tools(text, self._tools, request.tool_ids)
        skills = discover_skills(text)
        model = next((agent.model for agent in caller.agents if agent.tier != "director"), caller.agents[0].model)
        node_id = f"dyn_{uuid4().hex[:8]}"
        schema = _schema_name(node_id)
        return CrewNodeSpec.model_validate({
            "id": node_id, "kind": "crew", "label": f"On-the-fly · {request.role}", "process": "sequential",
            "agents": [{
                "id": f"{node_id}_agent", "role": request.role, "goal": request.goal, "tier": "specialist", "model": model,
                "backstory": f"You were spawned mid-run because the team lacked this capability. Deliver exactly what was asked and write every declared file.",
                "tool_ids": list(tools), "skill_ids": list(skills), "max_iterations": 8, "temperature": 0.2,
            }],
            "tasks": [{
                "id": f"{node_id}_task", "agent_id": f"{node_id}_agent", "description": request.task,
                "expected_output": "A complete deliverable with the list of files written.", "output_schema": schema,
                "output_schema_json": _deliverable_schema(schema), "expected_artifact_paths": list(paths),
            }],
        })

    def _sandbox_node(self, request: DynamicSpawnRequest, paths: tuple[str, ...]) -> NexusGenSandboxNodeSpec:
        if not paths:
            raise MutationError("A sandbox subtask must declare the files it writes")
        base = self._models[0] if self._models else "openai/gpt-4.1-mini"
        checks = " && ".join(f"test -s {path}" for path in paths)
        return NexusGenSandboxNodeSpec.model_validate({
            "id": f"dyn_{uuid4().hex[:8]}", "kind": "sandbox", "label": f"On-the-fly · {request.role}",
            "coder_model": base, "reviewer_model": base, "sandbox_provider": "docker", "max_rounds": 6, "timeout_seconds": 600,
            "coder_instructions": f"{request.goal} {request.task} Write each file relative to the working directory, creating folders as needed.",
            "reviewer_instructions": "Run the verification and confirm every declared file exists and is real.",
            "verification_command": checks or SANDBOX_VERIFY_DEFAULT, "expected_artifact_paths": list(paths),
        })

    async def _persist_record(self, spec: WorkflowSpec, record: SpawnRecord, request: DynamicSpawnRequest) -> dict[str, Any]:
        if record.kind != "specialist":
            raise MutationError("Only specialists can be persisted into the workflow; sandbox subtasks are one-off")
        handler = self._persist
        if handler is None:
            raise MutationError("Persisting a new specialist is not enabled for this run")
        operation = SpawnSpecialist(
            target_node_id=record.department_node_id, role=request.role, goal=request.goal, task_description=request.task,
            expected_artifact_paths=tuple(record.paths), tool_ids=tuple(request.tool_ids), rationale=request.rationale or "Spawned mid-run by a director",
        )
        try:
            evolved = self._mutator.apply(spec, [operation]).spec
        except MutationError as error:
            raise MutationError(f"The specialist ran, but cannot be added to {record.department_node_id}: {error}") from error
        return await handler(record, evolved)


class DynamicTeamMutatorTool(BaseTool):
    """Native tool handed to Tier-1 directors (and unmanaged Tier-2 leads) to extend the team during a run."""

    name: str = TOOL_ID
    description: str = (
        "Spawn a new specialist agent or a code/compilation sandbox subtask right now, when the current team has no one "
        "who owns a capability the product needs. The subtask runs immediately and its files appear in the run. "
        "Set persist=true to also propose adding the specialist to the permanent team."
    )
    args_schema: type[BaseModel] = DynamicSpawnRequest
    tool_id: str = TOOL_ID
    _spawner: DynamicSpawner = PrivateAttr()
    _loop: asyncio.AbstractEventLoop | None = PrivateAttr(default=None)

    def __init__(self, spawner: DynamicSpawner, **data: Any) -> None:
        super().__init__(**data)
        self._spawner = spawner
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    async def _arun(self, **arguments: Any) -> str:
        try:
            result = await self._spawner.spawn(DynamicSpawnRequest.model_validate(arguments))
        except (MutationError, ValueError) as error:
            return json.dumps({"error": str(error)})
        return json.dumps(result, default=str)

    def _run(self, **arguments: Any) -> str:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if self._loop is not None and self._loop.is_running():
            if running is self._loop:
                raise RuntimeError("Synchronous tool execution cannot block its owning event loop")
            return asyncio.run_coroutine_threadsafe(self._arun(**arguments), self._loop).result(timeout=1800)
        if running is None:
            return asyncio.run(self._arun(**arguments))
        raise RuntimeError("Use the asynchronous tool interface from an active event loop")

