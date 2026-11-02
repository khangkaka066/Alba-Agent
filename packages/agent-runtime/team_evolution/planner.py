"""Turn a bottleneck report into an ordered, conflict-free list of mutation operators."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from nexus_core_schema.models import AutoGenSandboxNodeSpec, CrewNodeSpec, WorkflowSpec

from .bottleneck_analyzer import declared_paths
from .domains import is_code_or_media
from .models import (
    BottleneckKind,
    BottleneckReport,
    Diagnosis,
    InjectQuality,
    MutationOp,
    PruneOrMerge,
    RewireParallel,
    SpawnSpecialist,
    SplitOverloaded,
)
from .topology_mutator import TeamTopologyMutator

LATENCY_FLOOR_SECONDS = 60.0
MAX_OPERATIONS = 6


@dataclass
class EvolutionPlan:
    operations: list[MutationOp] = field(default_factory=list)
    delegated: list[Diagnosis] = field(default_factory=list)

    @property
    def rationale(self) -> str:
        notes = [getattr(op, "rationale", "") for op in self.operations if getattr(op, "rationale", "")]
        return " ".join(dict.fromkeys(notes))[:1800]


def _first(items: Sequence[str]) -> str:
    return items[0] if items else ""


def plan_operations(
    report: BottleneckReport,
    spec: WorkflowSpec,
    *,
    available_tools: Collection[str] | None = None,
    available_models: Sequence[str] = (),
    optimize_latency: bool = True,
    max_operations: int = MAX_OPERATIONS,
) -> EvolutionPlan:
    nodes = {node.id: node for node in spec.nodes}
    owned = {path for node in spec.nodes if isinstance(node, (CrewNodeSpec, AutoGenSandboxNodeSpec)) for path in declared_paths(node)}
    prune: list[MutationOp] = []
    spawn: list[MutationOp] = []
    inject: list[MutationOp] = []
    extract: list[MutationOp] = []
    split: list[MutationOp] = []
    plan = EvolutionPlan()
    families = {name.split("/", 1)[0] for name in available_models}

    for item in report.diagnoses:
        node = nodes.get(item.node_id)
        evidence = _first(item.evidence)
        if item.kind is BottleneckKind.MISSING_SPECIALIST_ROLE and isinstance(node, CrewNodeSpec):
            paths = tuple(path for path in item.suggested_paths if path not in owned)
            spawn.append(SpawnSpecialist(
                target_node_id=item.node_id, role=item.suggested_role, goal=item.suggested_goal,
                task_description=(f"{item.suggested_goal[0].upper()}{item.suggested_goal[1:]}. Review the upstream results for this department, "
                                  f"fix what the quality review flagged and write {', '.join(paths) or 'your findings'}."),
                expected_artifact_paths=paths, tool_ids=item.suggested_tools, rationale=evidence,
            ))
            owned.update(paths)
        elif item.kind is BottleneckKind.OVERLOADED_NODE_BOTTLENECK and isinstance(node, CrewNodeSpec):
            code_paths = tuple(path for path in declared_paths(node) if is_code_or_media(path))
            if code_paths:
                extract.append(SplitOverloaded(target_node_id=item.node_id, mode="extract_sandbox", extract_paths=code_paths, rationale=evidence))
            else:
                split.append(SplitOverloaded(target_node_id=item.node_id, mode="parallel_crews", rationale=evidence))
        elif item.kind is BottleneckKind.MISSING_SANDBOX_OR_VERIFICATION_GATE and isinstance(node, CrewNodeSpec):
            failed_code = tuple(path for path in item.failed_paths if path in declared_paths(node))
            if failed_code:
                extract.append(SplitOverloaded(target_node_id=item.node_id, mode="extract_sandbox", extract_paths=failed_code, rationale=evidence))
            else:
                inject.append(InjectQuality(target_node_id=item.node_id, mode="critic", rationale=evidence))
        elif item.kind is BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT and node is not None:
            if item.agent_id is None:
                prune.append(PruneOrMerge(target_node_id=item.node_id, rationale=evidence))
            elif isinstance(node, CrewNodeSpec):
                agent = next((a for a in node.agents if a.id == item.agent_id), None)
                busy = {task.agent_id for task in node.tasks}
                siblings = [a for a in node.agents if a.id in busy and a.id not in (item.agent_id, node.manager_agent_id)]
                has_deliverable = any(task.expected_artifact_paths for task in node.tasks if task.agent_id == item.agent_id)
                merge = None
                if agent is not None and siblings and (has_deliverable or item.agent_id in busy):
                    merge = max(siblings, key=lambda other: len(set(other.tool_ids) & set(agent.tool_ids)) + len(set(other.skill_ids) & set(agent.skill_ids))).id
                prune.append(PruneOrMerge(target_node_id=item.node_id, agent_id=item.agent_id, merge_into_agent_id=merge, rationale=evidence))
        elif item.kind is BottleneckKind.SKILL_OR_PROMPT_DEFICIT:
            if item.route_to == "topology" and node is not None and node.kind in ("crew", "sandbox"):
                inject.append(InjectQuality(
                    target_node_id=item.node_id, mode="consensus" if len(families) >= 2 else "critic",
                    models=tuple(available_models[:3]), rationale=f"{evidence} (failed {item.repeat_count} runs)",
                ))
            else:
                plan.delegated.append(item)

    rewire: list[MutationOp] = []
    if optimize_latency and report.run_seconds >= LATENCY_FLOOR_SECONDS:
        mutator = TeamTopologyMutator(available_tools, available_models)
        rewire = [RewireParallel(target_node_id=node_id, rationale=f"Runs take {report.run_seconds:.0f}s and this step does not read its predecessor's output")
                  for node_id in mutator.find_parallelizable(spec)[:2]]

    seen: set[tuple[str, str, str | None]] = set()
    for operation in (*prune, *spawn, *inject, *rewire, *extract, *split):
        key = (operation.op, operation.target_node_id, getattr(operation, "agent_id", None) or getattr(operation, "role", None))
        if key in seen or len(plan.operations) >= max_operations:
            continue
        seen.add(key)
        plan.operations.append(operation)
    return plan
