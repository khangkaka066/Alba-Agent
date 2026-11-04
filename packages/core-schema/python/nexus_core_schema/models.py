"""Strict, portable specifications for tenant-scoped platform objects."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class ScopedContract(Contract):
    tenant_id: UUID
    workspace_id: UUID


ARTIFACT_PATH_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}(/[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}){0,7}$"
AgentTier = Literal["director", "lead", "specialist"]
JoinMode = Literal["any", "all"]
RigorMode = Literal["minimal", "standard", "full_studio"]
ChannelId = Literal["tiktok", "facebook", "youtube"]
ArtifactPath = Annotated[str, Field(min_length=1, max_length=240, pattern=ARTIFACT_PATH_PATTERN)]


def _unique_artifact_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    if len(paths) != len(set(paths)):
        raise ValueError("Expected artifact paths must be unique")
    if any(".." in path.split("/") for path in paths):
        raise ValueError("Expected artifact paths must stay inside the run artifact directory")
    return paths


class NodePosition(Contract):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class AgentSpec(Contract):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    role: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1)
    backstory: str = ""
    model: str = Field(min_length=1)
    tool_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    max_iterations: int = Field(default=10, ge=1, le=100)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    guardrails: tuple[str, ...] = ()
    knowledge_capsule_ids: tuple[UUID, ...] = ()
    tier: AgentTier | None = None


class TaskSpec(Contract):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    agent_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    output_schema: str = Field(min_length=1)
    output_schema_json: dict[str, Any] | None = None
    context_task_ids: tuple[str, ...] = ()
    expected_artifact_paths: tuple[ArtifactPath, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> TaskSpec:
        _unique_artifact_paths(self.expected_artifact_paths)
        return self


class ConsensusConfigSpec(Contract):
    enabled: bool = False
    models: tuple[str, ...] = Field(default=(), min_length=0, max_length=8)
    arbiter_model: str = ""
    min_agreement_threshold: float = Field(default=0.85, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_consensus_models(self) -> ConsensusConfigSpec:
        if self.enabled and (len(self.models) < 2 or not self.arbiter_model):
            raise ValueError("Enabled consensus requires at least two models and an arbiter model")
        return self


class StartNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["start"] = "start"
    label: str = "Start"
    trigger_type: Literal["manual", "webhook", "schedule", "bot"] = "manual"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = None


class CrewNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["crew"] = "crew"
    label: str = Field(min_length=1)
    agents: tuple[AgentSpec, ...] = Field(min_length=1)
    tasks: tuple[TaskSpec, ...] = Field(min_length=1)
    process: Literal["sequential", "hierarchical"] = "sequential"
    consensus_config: ConsensusConfigSpec = Field(default_factory=ConsensusConfigSpec)
    manager_agent_id: str | None = None
    join: JoinMode = "any"
    expected_artifact_paths: tuple[ArtifactPath, ...] = Field(default=(), max_length=64)
    requires_visual_evidence: bool = False

    @model_validator(mode="after")
    def validate_references(self) -> CrewNodeSpec:
        agent_ids = [agent.id for agent in self.agents]
        task_ids = [task.id for task in self.tasks]
        if len(agent_ids) != len(set(agent_ids)) or len(task_ids) != len(set(task_ids)):
            raise ValueError("Agent and task IDs must be unique within a crew node")
        if any(task.agent_id not in agent_ids for task in self.tasks):
            raise ValueError("Every task must reference an agent in its crew node")
        if any(ref not in task_ids for task in self.tasks for ref in task.context_task_ids):
            raise ValueError("Task context must reference a task in its crew node")
        if self.manager_agent_id is not None:
            if self.process != "hierarchical":
                raise ValueError("A crew manager agent requires the hierarchical process")
            manager = next((agent for agent in self.agents if agent.id == self.manager_agent_id), None)
            if manager is None:
                raise ValueError("Crew manager agent must be one of the crew agents")
            if manager.tool_ids:
                raise ValueError("A crew manager agent delegates work and cannot hold tools")
            if any(task.agent_id == manager.id for task in self.tasks):
                raise ValueError("Tasks must be assigned to specialists, not the crew manager")
            if len(self.agents) < 2:
                raise ValueError("A managed crew needs at least one specialist")
        _unique_artifact_paths(self.expected_artifact_paths)
        return self

    def declared_artifact_paths(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.expected_artifact_paths, *(path for task in self.tasks for path in task.expected_artifact_paths))))


class NexusGenSandboxNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["sandbox"] = "sandbox"
    label: str = Field(min_length=1)
    coder_model: str = Field(min_length=1)
    reviewer_model: str = Field(min_length=1)
    sandbox_provider: Literal["docker", "e2b", "daytona"] = "docker"
    coder_instructions: str = ""
    reviewer_instructions: str = ""
    tool_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    computer_id: UUID | None = None
    max_rounds: int = Field(default=8, ge=1, le=50)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    verification_command: str = Field(min_length=1)
    # What to do when the code ran but no executable evidence proves it: hand it over clearly labelled, or fail the run.
    on_unverified: Literal["deliver_labeled", "fail"] = "deliver_labeled"
    consensus_config: ConsensusConfigSpec = Field(default_factory=ConsensusConfigSpec)
    join: JoinMode = "any"
    expected_artifact_paths: tuple[ArtifactPath, ...] = Field(default=(), max_length=64)
    requires_visual_evidence: bool = False

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> NexusGenSandboxNodeSpec:
        _unique_artifact_paths(self.expected_artifact_paths)
        return self

    def declared_artifact_paths(self) -> tuple[str, ...]:
        return self.expected_artifact_paths


class ApprovalGateNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["approval"] = "approval"
    label: str = Field(min_length=1)
    action_description: str = Field(min_length=1)
    required_role: Literal["owner", "admin", "builder"] = "admin"
    timeout_seconds: int = Field(default=86400, ge=60)
    boundary_rules: tuple[str, ...] = ()


class RouteSpec(Contract):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    field_path: str = Field(min_length=1)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "exists"]
    value: str | int | float | bool | None = None


class RouterNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["router"] = "router"
    label: str = Field(min_length=1)
    routes: tuple[RouteSpec, ...] = Field(min_length=1)
    default_route: str = Field(min_length=1)
    artifact_gate: bool = False
    max_loop_iterations: int = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def validate_routes(self) -> RouterNodeSpec:
        names = [route.name for route in self.routes]
        if len(names) != len(set(names)) or self.default_route in names:
            raise ValueError("Router route names and default route must be distinct")
        return self

    def gate_key(self) -> str:
        """State key holding this router's deterministic artifact-gate verdict."""
        return f"{self.id}__gate"


class RAGNodeSpec(Contract):
    id: str = Field(min_length=1)
    kind: Literal["rag"] = "rag"
    label: str = Field(min_length=1)
    knowledge_base_id: UUID
    query_template: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    mcp_server_ids: tuple[str, ...] = ()


WorkflowNode = Annotated[
    StartNodeSpec
    | CrewNodeSpec
    | NexusGenSandboxNodeSpec
    | ApprovalGateNodeSpec
    | RouterNodeSpec
    | RAGNodeSpec,
    Field(discriminator="kind"),
]


class WorkflowEdgeSpec(Contract):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    route: str | None = None
    loop_back: bool = False


class PropagationScope(str, Enum):
    AGENT_PRIVATE = "AGENT_PRIVATE"
    CREW_LOCAL = "CREW_LOCAL"
    WORKFLOW_SCOPED = "WORKFLOW_SCOPED"
    WORKSPACE_QUARANTINE = "WORKSPACE_QUARANTINE"
    WORKSPACE_VERIFIED = "WORKSPACE_VERIFIED"


class SensitivityLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL_PII_STRIPPED = "CONFIDENTIAL_PII_STRIPPED"


class LearningEdgeSpec(Contract):
    source_agent_id: str = Field(min_length=1, max_length=100)
    target_agent_id: str = Field(min_length=1, max_length=100)
    scope: PropagationScope = PropagationScope.CREW_LOCAL
    allow_heuristics: bool = True
    allow_code_patterns: bool = False
    require_human_approval: bool = False


class PathRuleSpec(Contract):
    """A content or coding standard injected for agents writing to matching artifact paths."""

    pattern: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_*./-]+$")
    rule: str = Field(min_length=1, max_length=2000)


class WorkflowModesSpec(Contract):
    rigor: RigorMode = "minimal"
    path_rules: tuple[PathRuleSpec, ...] = Field(default=(), max_length=64)
    # Social channels this team publishes to. The app shows channel connection only to people who use such a team.
    channels: tuple[ChannelId, ...] = Field(default=(), max_length=3)


class WorkflowSpec(ScopedContract):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdgeSpec, ...] = ()
    learning_edges: tuple[LearningEdgeSpec, ...] = ()
    layout: dict[str, NodePosition] = Field(default_factory=dict)
    modes: WorkflowModesSpec = Field(default_factory=WorkflowModesSpec)

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowSpec:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Workflow node IDs must be unique")
        if self.layout and set(self.layout) != set(node_ids):
            raise ValueError("Workflow layout must position every node exactly once")
        starts = [node for node in self.nodes if node.kind == "start"]
        if len(starts) != 1:
            raise ValueError("Workflow must contain exactly one start node")
        nodes_by_id = {node.id: node for node in self.nodes}
        for edge in self.edges:
            if edge.source not in nodes_by_id or edge.target not in nodes_by_id:
                raise ValueError("Workflow edge references an unknown node")
            if edge.target == starts[0].id:
                raise ValueError("Start node cannot have incoming edges")
            source = nodes_by_id[edge.source]
            if isinstance(source, RouterNodeSpec):
                valid_routes = {route.name for route in source.routes} | {source.default_route}
                if edge.route not in valid_routes:
                    raise ValueError("Router edge must name a declared route")
            elif edge.route is not None:
                raise ValueError("Only router edges may name a route")
            if edge.loop_back:
                if not isinstance(source, RouterNodeSpec) or source.max_loop_iterations < 1:
                    raise ValueError("Loop-back edges must leave a router with a loop budget")
                if edge.target == edge.source:
                    raise ValueError("A loop-back edge must target an earlier node")
        forward_routes = {(edge.source, edge.route) for edge in self.edges if not edge.loop_back}
        if any((edge.source, edge.route) in forward_routes for edge in self.edges if edge.loop_back):
            raise ValueError("A router route cannot both continue forward and loop back")
        agent_ids = {agent.id for node in self.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents}
        source_ids = agent_ids | {f"{node.id}_coder" for node in self.nodes if isinstance(node, NexusGenSandboxNodeSpec)}
        if any(edge.source_agent_id not in source_ids or edge.target_agent_id not in agent_ids for edge in self.learning_edges):
            raise ValueError("Learning edge references an unknown agent")
        if any(edge.source_agent_id == edge.target_agent_id for edge in self.learning_edges):
            raise ValueError("Learning edges must connect distinct agents")
        return self


def forward_edges(spec: WorkflowSpec) -> tuple[WorkflowEdgeSpec, ...]:
    """Edges that define execution order; router loop-back edges are handled by the runtime."""
    return tuple(edge for edge in spec.edges if not edge.loop_back)


class KnowledgeCapsuleSpec(ScopedContract):
    capsule_id: UUID
    source_agent_id: str = Field(min_length=1, max_length=100)
    source_role: str = Field(min_length=1, max_length=200)
    source_domain_tags: tuple[str, ...] = ()
    trigger_preconditions: str = Field(min_length=1, max_length=4000)
    distilled_heuristic: str = Field(min_length=1, max_length=8000)
    prohibited_contexts: tuple[str, ...] = ()
    propagation_scope: PropagationScope = PropagationScope.AGENT_PRIVATE
    sensitivity_level: SensitivityLevel = SensitivityLevel.INTERNAL
    source_workflow_id: UUID | None = None
    source_crew_id: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class LearningMetricSample(Contract):
    success_rate: float = Field(ge=0, le=1)
    retry_and_error_turns: float = Field(ge=0)
    human_approval_rejection_rate: float = Field(ge=0, le=1)
    token_count: float = Field(ge=0)
    latency_ms: float = Field(ge=0)


class TransferTelemetrySpec(ScopedContract):
    run_id: UUID
    capsule_id: UUID
    source_agent_id: str = Field(min_length=1, max_length=100)
    target_agent_id: str = Field(min_length=1, max_length=100)
    condition: Literal["baseline", "treatment"]
    success: bool
    retry_and_error_turns: int = Field(default=0, ge=0)
    human_approval_rejected: bool = False
    token_count: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    target_domain_tags: tuple[str, ...] = ()


class MarkdownRoutineSpec(ScopedContract):
    id: UUID
    bot_id: UUID
    name: str = Field(min_length=1)
    instruction_markdown: str = Field(min_length=1)
    cron_expression: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    enabled: bool = True
    workflow_id: UUID | None = None
    interval_seconds: int | None = Field(default=None, ge=1)


class PersistentBotSpec(ScopedContract):
    id: UUID
    name: str = Field(min_length=1)
    description: str = ""
    model: str = Field(min_length=1)
    tool_ids: tuple[str, ...] = ()
    memory_namespace: str = Field(min_length=1)
    routine_ids: tuple[UUID, ...] = ()
    credential_id: UUID | None = None
    billing_mode: Literal["platform", "byok"] = "platform"
    api_base: str | None = None


class ApprovalRequestSpec(ScopedContract):
    id: UUID
    run_id: UUID
    node_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_role: Literal["owner", "admin", "builder"] = "admin"
    status: Literal["pending", "allowed_once", "always_allowed", "denied"] = "pending"
    expires_at: datetime | None = None


class SandboxComputerSpec(ScopedContract):
    id: UUID
    provider: Literal["docker", "e2b", "daytona", "createos", "boat", "railway"]
    visibility: Literal["private", "shared"]
    bot_id: UUID | None = None
    run_id: UUID | None = None
    cpu_limit: float = Field(default=1.0, gt=0, le=64)
    memory_mb: int = Field(default=1024, ge=128, le=131072)
    idle_timeout_seconds: int = Field(default=1800, ge=60)


class RuntimeEventType(str, Enum):
    FLOW_STATE_CHANGED = "FLOW_STATE_CHANGED"
    CREW_AGENT_THOUGHT = "CREW_AGENT_THOUGHT"
    TOOL_INVOKED = "TOOL_INVOKED"
    NEXUSGEN_CODE_GENERATED = "NEXUSGEN_CODE_GENERATED"
    SANDBOX_TERMINAL_OUTPUT = "SANDBOX_TERMINAL_OUTPUT"
    SANDBOX_SCREEN_FRAME = "SANDBOX_SCREEN_FRAME"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    NEGATIVE_TRANSFER_DETECTED = "NEGATIVE_TRANSFER_DETECTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"


class RuntimeEvent(ScopedContract):
    id: UUID
    run_id: UUID
    node_id: str | None = None
    type: RuntimeEventType
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
