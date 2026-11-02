"""Typed contracts for team diagnostics, structural mutation operators and topology diffs."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus_core_schema.models import ARTIFACT_PATH_PATTERN

ArtifactPathStr = Annotated[str, Field(min_length=1, max_length=240, pattern=ARTIFACT_PATH_PATTERN)]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BottleneckKind(str, Enum):
    SKILL_OR_PROMPT_DEFICIT = "SKILL_OR_PROMPT_DEFICIT"
    MISSING_SPECIALIST_ROLE = "MISSING_SPECIALIST_ROLE"
    OVERLOADED_NODE_BOTTLENECK = "OVERLOADED_NODE_BOTTLENECK"
    MISSING_SANDBOX_OR_VERIFICATION_GATE = "MISSING_SANDBOX_OR_VERIFICATION_GATE"
    REDUNDANT_OR_NEGATIVE_AGENT = "REDUNDANT_OR_NEGATIVE_AGENT"


class OpKind(str, Enum):
    SPAWN_SPECIALIST_AGENT = "SPAWN_SPECIALIST_AGENT"
    SPLIT_OVERLOADED_CREW_OR_SANDBOX = "SPLIT_OVERLOADED_CREW_OR_SANDBOX"
    INJECT_QUALITY_CRITIC_OR_CONSENSUS = "INJECT_QUALITY_CRITIC_OR_CONSENSUS"
    PRUNE_OR_MERGE_REDUNDANT_AGENT = "PRUNE_OR_MERGE_REDUNDANT_AGENT"
    REWIRE_SEQUENTIAL_TO_PARALLEL = "REWIRE_SEQUENTIAL_TO_PARALLEL"


# --- observations -----------------------------------------------------------------------------------------------

class HumanFeedback(Frozen):
    node_id: str | None = None
    decision: Literal["denied", "edited", "approved"] = "denied"
    comment: str = Field(default="", max_length=4000)


class RunObservation(Frozen):
    """Everything the analyzer needs to know about one finished (or failed) run."""

    run_id: str
    status: Literal["completed", "failed", "paused", "cancelled", "running", "queued"] = "completed"
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    completed_nodes: tuple[str, ...] = ()
    node_seconds: dict[str, float] = Field(default_factory=dict)
    node_cost_usd: dict[str, float] = Field(default_factory=dict)
    run_seconds: float | None = None
    total_cost_usd: float | None = None
    failure_message: str | None = None
    human_feedback: tuple[HumanFeedback, ...] = ()


class Diagnosis(Frozen):
    kind: BottleneckKind
    node_id: str
    agent_id: str | None = None
    severity: float = Field(ge=0.0, le=1.0)
    evidence: tuple[str, ...] = ()
    repeat_count: int = Field(default=1, ge=1)
    failed_paths: tuple[str, ...] = ()
    suggested_role: str = ""
    suggested_goal: str = ""
    suggested_paths: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    suggested_skills: tuple[str, ...] = ()
    route_to: Literal["topology", "self_healing", "skills"] = "topology"


class BottleneckReport(Frozen):
    workflow_id: str
    runs_analyzed: int
    diagnoses: tuple[Diagnosis, ...] = ()
    run_seconds: float = 0.0

    def of_kind(self, kind: BottleneckKind) -> tuple[Diagnosis, ...]:
        return tuple(item for item in self.diagnoses if item.kind == kind)

    @property
    def needs_topology_change(self) -> bool:
        return any(item.route_to == "topology" for item in self.diagnoses)


# --- operators --------------------------------------------------------------------------------------------------

class SpawnSpecialist(Frozen):
    op: Literal["SPAWN_SPECIALIST_AGENT"] = "SPAWN_SPECIALIST_AGENT"
    target_node_id: str
    role: str = Field(min_length=2, max_length=200)
    goal: str = Field(min_length=5, max_length=2000)
    task_description: str = Field(min_length=5, max_length=4000)
    expected_artifact_paths: tuple[ArtifactPathStr, ...] = Field(default=(), max_length=8)
    tool_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    model: str | None = None
    rationale: str = Field(default="", max_length=2000)


class SplitOverloaded(Frozen):
    op: Literal["SPLIT_OVERLOADED_CREW_OR_SANDBOX"] = "SPLIT_OVERLOADED_CREW_OR_SANDBOX"
    target_node_id: str
    mode: Literal["parallel_crews", "extract_sandbox"] = "parallel_crews"
    extract_paths: tuple[ArtifactPathStr, ...] = Field(default=(), max_length=32)
    rationale: str = Field(default="", max_length=2000)


class InjectQuality(Frozen):
    op: Literal["INJECT_QUALITY_CRITIC_OR_CONSENSUS"] = "INJECT_QUALITY_CRITIC_OR_CONSENSUS"
    target_node_id: str
    mode: Literal["critic", "consensus"] = "critic"
    models: tuple[str, ...] = ()
    arbiter_model: str = ""
    rationale: str = Field(default="", max_length=2000)


class PruneOrMerge(Frozen):
    op: Literal["PRUNE_OR_MERGE_REDUNDANT_AGENT"] = "PRUNE_OR_MERGE_REDUNDANT_AGENT"
    target_node_id: str
    agent_id: str | None = None
    merge_into_agent_id: str | None = None
    rationale: str = Field(default="", max_length=2000)


class RewireParallel(Frozen):
    op: Literal["REWIRE_SEQUENTIAL_TO_PARALLEL"] = "REWIRE_SEQUENTIAL_TO_PARALLEL"
    target_node_id: str
    rationale: str = Field(default="", max_length=2000)


MutationOp = Annotated[
    SpawnSpecialist | SplitOverloaded | InjectQuality | PruneOrMerge | RewireParallel,
    Field(discriminator="op"),
]


class AppliedOp(Frozen):
    op: OpKind
    target_node_id: str
    summary: str
    rationale: str = ""
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    modified_nodes: tuple[str, ...] = ()
    added_agents: tuple[str, ...] = ()
    removed_agents: tuple[str, ...] = ()
    request: dict[str, Any] = Field(default_factory=dict)


class TopologyDiff(Frozen):
    added_nodes: tuple[str, ...] = ()
    modified_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    added_agents: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    removed_agents: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    added_edges: tuple[tuple[str, str], ...] = ()
    removed_edges: tuple[tuple[str, str], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.added_nodes or self.modified_nodes or self.removed_nodes or self.added_edges or self.removed_edges)

    def lines(self) -> list[str]:
        """Human-readable diff lines for proposal cards."""
        lines = [f"+ node {node}" for node in self.added_nodes]
        lines += [f"~ node {node}" for node in self.modified_nodes]
        lines += [f"- node {node}" for node in self.removed_nodes]
        for node, roles in self.added_agents.items():
            lines += [f"+ agent {role} in {node}" for role in roles]
        for node, roles in self.removed_agents.items():
            lines += [f"- agent {role} from {node}" for role in roles]
        return lines
