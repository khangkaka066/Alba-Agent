"""Three-tier studio blueprints and the deterministic graph builder shared by templates and the Meta-Architect."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from nexus_core_schema.models import (
    AgentSpec,
    AgentTier,
    ApprovalGateNodeSpec,
    AutoGenSandboxNodeSpec,
    ChannelId,
    CrewNodeSpec,
    NodePosition,
    PathRuleSpec,
    RouteSpec,
    RouterNodeSpec,
    StartNodeSpec,
    TaskSpec,
    WorkflowEdgeSpec,
    WorkflowModesSpec,
    WorkflowNode,
)

StudioRigor = Literal["standard", "full_studio"]
StudioDomain = Literal["game", "video", "film", "marketing", "analytics", "software", "report"]

# Standard rigor keeps two directors, two parallel departments and one sandbox: 9 nodes, 19 agents.
STANDARD_DIRECTORS = 2
STANDARD_WAVE_ONE_SPECIALISTS = 4
STANDARD_QA_SPECIALISTS = 2
STANDARD_RELEASE_SPECIALISTS = 1
LAYER_WIDTH = 340
ROW_HEIGHT = 310
CENTER_Y = 560


@dataclass(frozen=True)
class StudioRole:
    key: str
    role: str
    focus: str
    artifact: str
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class StudioDepartment:
    key: str
    label: str
    purpose: str
    lead: StudioRole | None = None
    specialists: tuple[StudioRole, ...] = ()
    kind: Literal["crew", "sandbox"] = "crew"
    artifacts: tuple[str, ...] = ()
    instructions: str = ""
    review: str = ""
    verification: str = "python -m compileall -q ."
    visual_evidence: bool = False


@dataclass(frozen=True)
class StudioBlueprint:
    id: str
    title: str
    domain: StudioDomain
    summary: str
    description: str
    tags: tuple[str, ...]
    directors: tuple[StudioRole, ...]
    wave_one: tuple[StudioDepartment, ...]
    wave_two: tuple[StudioDepartment, ...]
    qa: StudioDepartment
    release: StudioDepartment
    path_rules: tuple[PathRuleSpec, ...] = ()
    standard_wave_one: tuple[str, ...] = ()
    standard_wave_two: str = ""
    readiness_notes: tuple[str, ...] = ()
    channels: tuple[ChannelId, ...] = ()

    def departments(self, rigor: StudioRigor) -> tuple[tuple[StudioDepartment, ...], tuple[StudioDepartment, ...]]:
        if rigor == "full_studio":
            return self.wave_one, self.wave_two
        wave_one = tuple(dept for dept in self.wave_one if dept.key in self.standard_wave_one)
        wave_two = tuple(dept for dept in self.wave_two if dept.key == self.standard_wave_two)
        return wave_one, wave_two


@dataclass
class StudioGraph:
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdgeSpec]
    layout: dict[str, NodePosition]
    modes: WorkflowModesSpec
    agent_count: int
    departments: list[dict[str, Any]] = field(default_factory=list)


def _schema_name(*parts: str) -> str:
    return "Studio" + "".join(re.sub(r"[^A-Za-z0-9]", "", part.title()) for part in parts) + "Output"


def _deliverable_schema(name: str, *, gate: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "summary": {"type": "string"},
        "content": {"type": "string"},
        "files_written": {"type": "array", "items": {"type": "string"}},
        "open_risks": {"type": "string"},
    }
    required = ["summary", "content", "files_written"]
    if gate:
        properties["gate_passed"] = {"type": "boolean"}
        properties["failing_department"] = {"type": "string"}
        required += ["gate_passed", "failing_department"]
    return {"title": name, "type": "object", "additionalProperties": False, "properties": properties, "required": required}


def _agent(role: StudioRole, tier: AgentTier, model: str, tools: Collection[str] | None, prefix: str) -> AgentSpec:
    allowed = tuple(tool for tool in role.tools if tools is None or tool in tools) if tier != "lead" else ()
    return AgentSpec(
        id=f"{prefix}_{role.key}", role=role.role, tier=tier, model=model,
        goal=f"{role.focus[0].upper()}{role.focus[1:]}.",
        backstory=(
            f"You are the studio's {role.role}. You own {role.artifact} and hold it to a production standard: "
            "complete, specific to this request and consistent with the master brief. You never claim a file exists "
            "unless you wrote it."
        ),
        tool_ids=allowed, skill_ids=role.skills,
        temperature=0.3 if tier == "director" else 0.2,
        max_iterations=8 if tier == "specialist" else 12,
    )


def _task(dept_id: str, role: StudioRole, purpose: str, objective: str, prefix: str, *, gate_targets: tuple[str, ...] = ()) -> TaskSpec:
    name = _schema_name(dept_id, role.key)
    description = (
        f"{role.focus[0].upper()}{role.focus[1:]} for the requested product. Department objective: {purpose}"
        + (f" Project-specific direction: {objective}" if objective else "")
        + f" Write the finished deliverable to {role.artifact}. Build on the master brief and the artifact registry from upstream results."
    )
    if gate_targets:
        description += (
            " Then audit the evidence pack: confirm every file in the artifact registry exists and inspect the rendered previews in qa/evidence/. "
            "Set gate_passed to false when any deliverable is missing, empty or below the quality bar, and set failing_department to exactly one of: "
            + ", ".join(gate_targets) + ". Use an empty string when the gate passes."
        )
    return TaskSpec(
        id=f"{prefix}_{role.key}_task", agent_id=f"{prefix}_{role.key}", description=description,
        expected_output=f"A complete deliverable saved at {role.artifact}, with a summary and the list of files written.",
        output_schema=name, output_schema_json=_deliverable_schema(name, gate=bool(gate_targets)),
        expected_artifact_paths=(role.artifact,),
    )


def _crew(dept: StudioDepartment, specialists: tuple[StudioRole, ...], model: str, lead_model: str,
          tools: Collection[str] | None, objective: str, *, gate_targets: tuple[str, ...] = ()) -> CrewNodeSpec:
    assert dept.lead is not None
    prefix = dept.key
    agents = (_agent(dept.lead, "lead", lead_model, tools, prefix), *(_agent(role, "specialist", model, tools, prefix) for role in specialists))
    tasks = tuple(
        _task(dept.key, role, dept.purpose, objective, prefix, gate_targets=gate_targets if index == len(specialists) - 1 else ())
        for index, role in enumerate(specialists)
    )
    return CrewNodeSpec(
        id=dept.key, label=dept.label, agents=agents, tasks=tasks, process="hierarchical",
        manager_agent_id=agents[0].id, join="all", expected_artifact_paths=dept.artifacts,
        requires_visual_evidence=dept.visual_evidence,
    )


def build_studio_graph(
    blueprint: StudioBlueprint,
    rigor: StudioRigor,
    *,
    model: str,
    director_model: str,
    tools: Collection[str] | None = None,
    objectives: Mapping[str, str] | None = None,
    requirement: str = "",
) -> StudioGraph:
    """Assemble the layered studio DAG: directors, parallel departments, parallel sandboxes, QA, gate,
    sign-off and release. ``tools`` limits agent tools to those enabled in the workspace (``None`` keeps all)."""
    goals = dict(objectives or {})
    wave_one, wave_two = blueprint.departments(rigor)
    full = rigor == "full_studio"
    directors = blueprint.directors if full else blueprint.directors[:STANDARD_DIRECTORS]
    director_agents = tuple(_agent(role, "director", director_model, tools, "direction") for role in directors)
    brief = goals.get("direction", "")
    request_note = f" The request is: {requirement[:1500]}" if requirement else ""
    director_tasks = tuple(
        TaskSpec(
            id=f"direction_{role.key}_task", agent_id=f"direction_{role.key}",
            description=(
                f"{role.focus[0].upper()}{role.focus[1:]}.{request_note}"
                + (f" Direction: {brief}" if brief else "")
                + f" Write it to {role.artifact}. Name every department deliverable and its exact artifact path so each team has a binding artifact contract."
            ),
            expected_output=f"An authoritative document saved at {role.artifact}.",
            output_schema=_schema_name("direction", role.key),
            output_schema_json=_deliverable_schema(_schema_name("direction", role.key)),
            expected_artifact_paths=(role.artifact,),
            context_task_ids=tuple(f"direction_{prior.key}_task" for prior in directors[:index]),
        )
        for index, role in enumerate(directors)
    )
    nodes: list[WorkflowNode] = [
        StartNodeSpec(id="start", label="Studio request", input_schema={"type": "object", "properties": {"task": {"type": "string"}}}),
        CrewNodeSpec(
            id="direction", label="Tier 1 · Studio directors", agents=director_agents, tasks=director_tasks,
            expected_artifact_paths=("production/artifact_registry.json",),
        ),
    ]
    department_summary: list[dict[str, Any]] = [{"id": "direction", "label": "Tier 1 · Studio directors", "agents": len(director_agents)}]
    for dept in wave_one:
        specialists = dept.specialists if full else dept.specialists[:STANDARD_WAVE_ONE_SPECIALISTS]
        nodes.append(_crew(dept, specialists, model, director_model, tools, goals.get(dept.key, "")))
        department_summary.append({"id": dept.key, "label": dept.label, "agents": 1 + len(specialists)})
    for dept in wave_two:
        nodes.append(AutoGenSandboxNodeSpec(
            id=dept.key, label=dept.label, coder_model=model, reviewer_model=director_model,
            coder_instructions=dept.instructions + (f" Project-specific direction: {goals[dept.key]}" if goals.get(dept.key) else ""),
            reviewer_instructions=dept.review, sandbox_provider="docker", max_rounds=8, timeout_seconds=900,
            verification_command=dept.verification, join="all", expected_artifact_paths=dept.artifacts,
            requires_visual_evidence=dept.visual_evidence,
        ))
        department_summary.append({"id": dept.key, "label": dept.label, "agents": 2})
    rework_targets = tuple(dept.key for dept in (*wave_one, *wave_two))
    qa_specialists = blueprint.qa.specialists if full else blueprint.qa.specialists[-STANDARD_QA_SPECIALISTS:]
    nodes.append(_crew(blueprint.qa, qa_specialists, model, director_model, tools, goals.get(blueprint.qa.key, ""), gate_targets=rework_targets))
    department_summary.append({"id": blueprint.qa.key, "label": blueprint.qa.label, "agents": 1 + len(qa_specialists)})
    gate = RouterNodeSpec(
        id="quality_gate", label="Quality gate & artifact verification",
        routes=(
            RouteSpec(name="pass", field_path="quality_gate__gate.gate_passed", operator="eq", value=True),
            *(RouteSpec(name=f"rework_{target}", field_path="quality_gate__gate.failing_department", operator="eq", value=target)
              for target in rework_targets),
        ),
        default_route="escalate", artifact_gate=True, max_loop_iterations=2 if full else 1,
    )
    nodes.append(gate)
    nodes.append(ApprovalGateNodeSpec(
        id="sign_off", label="Executive Producer sign-off",
        action_description="Review the evidence pack in qa/, the quality-gate verdict and every deliverable before release.",
        required_role="admin", boundary_rules=("external_action", "high_spend"),
    ))
    release_specialists = blueprint.release.specialists if full else blueprint.release.specialists[:STANDARD_RELEASE_SPECIALISTS]
    nodes.append(_crew(blueprint.release, release_specialists, model, director_model, tools, goals.get(blueprint.release.key, "")))
    department_summary.append({"id": blueprint.release.key, "label": blueprint.release.label, "agents": 1 + len(release_specialists)})

    edges: list[WorkflowEdgeSpec] = [WorkflowEdgeSpec(source="start", target="direction")]
    edges += [WorkflowEdgeSpec(source="direction", target=dept.key) for dept in wave_one]
    edges += [WorkflowEdgeSpec(source=source.key, target=target.key) for target in wave_two for source in wave_one]
    edges += [WorkflowEdgeSpec(source=source.key, target=blueprint.qa.key) for source in wave_two]
    edges.append(WorkflowEdgeSpec(source=blueprint.qa.key, target="quality_gate"))
    edges.append(WorkflowEdgeSpec(source="quality_gate", target="sign_off", route="pass"))
    edges += [WorkflowEdgeSpec(source="quality_gate", target=target, route=f"rework_{target}", loop_back=True) for target in rework_targets]
    edges.append(WorkflowEdgeSpec(source="quality_gate", target="direction", route="escalate", loop_back=True))
    edges.append(WorkflowEdgeSpec(source="sign_off", target=blueprint.release.key))

    layers: list[list[str]] = [
        ["start"], ["direction"], [dept.key for dept in wave_one], [dept.key for dept in wave_two],
        [blueprint.qa.key], ["quality_gate"], ["sign_off"], [blueprint.release.key],
    ]
    layout: dict[str, NodePosition] = {}
    for column, layer in enumerate(layers):
        top = CENTER_Y - (len(layer) - 1) * ROW_HEIGHT / 2
        for row, node_id in enumerate(layer):
            layout[node_id] = NodePosition(x=60 + column * LAYER_WIDTH, y=top + row * ROW_HEIGHT)
    agent_count = sum(len(node.agents) if isinstance(node, CrewNodeSpec) else 2 for node in nodes if isinstance(node, (CrewNodeSpec, AutoGenSandboxNodeSpec)))
    return StudioGraph(
        nodes=nodes, edges=edges, layout=layout,
        modes=WorkflowModesSpec(rigor=rigor, path_rules=blueprint.path_rules, channels=blueprint.channels),
        agent_count=agent_count, departments=department_summary,
    )
