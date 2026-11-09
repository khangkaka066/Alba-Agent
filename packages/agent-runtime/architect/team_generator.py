"""Structured, validated synthesis for workflow graphs and persistent teammates."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, Mapping, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from architect.adaptive import Assessment, assess, build_solo_workflow, is_small_script_request
from architect.units import MAX_UNITS, MIN_UNITS, UnitsDraft, build_units_workflow
from hooks.claims import deliverables_in
from nexus_core_schema_templates.studios import STUDIO_BLUEPRINTS, STUDIO_BY_ID, StudioBlueprint, build_studio_graph, detect_studio
from nexus_core_schema.models import (
    AgentSpec,
    ApprovalGateNodeSpec,
    NexusGenSandboxNodeSpec,
    CrewNodeSpec,
    KnowledgeCapsuleSpec,
    LearningEdgeSpec,
    MarkdownRoutineSpec,
    NodePosition,
    PersistentBotSpec,
    PropagationScope,
    RAGNodeSpec,
    StartNodeSpec,
    TaskSpec,
    WorkflowEdgeSpec,
    WorkflowSpec,
)


class ToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    server_id: str = Field(min_length=1, max_length=120)


class KnowledgeBaseDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    name: str


class VerifiedCapsuleDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    capsule: KnowledgeCapsuleSpec
    impact_score: float = Field(ge=0, le=1)


class ArchitectWorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: UUID
    workspace_id: UUID
    available_models: tuple[str, ...] = ()
    # Models the user chose as their defaults (a connected provider lists everything it knows, some of which answer 404):
    # the only ones known to work, so the fallback and the consensus pair come from here first.
    trusted_models: tuple[str, ...] = ()
    mcp_tools: tuple[ToolDescriptor, ...] = ()
    knowledge_bases: tuple[KnowledgeBaseDescriptor, ...] = ()
    verified_capsules: tuple[VerifiedCapsuleDescriptor, ...] = ()
    output_schema_names: tuple[str, ...] = ("NexusTextResult",)
    skill_slugs: tuple[str, ...] = ()
    skill_keywords: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    builtin_tool_ids: tuple[str, ...] = ()

    @property
    def fallback_model(self) -> str:
        """The model used when none is requested: the user's own default, never just the first name in a long list."""
        return (self.trusted_models or self.available_models or ("openai/gpt-4.1-mini",))[0]

    def frontier_model(self, fallback: str) -> str:
        """A frontier-class model for the hard parts (repair attempt, directors): the first one among the models known to work,
        else `fallback`. Searching the whole list by keyword also finds names the provider lists but cannot serve."""
        pool = self.trusted_models or self.available_models
        return next((name for name in pool if any(hint in name for hint in _FRONTIER_MODEL_HINTS) and "mini" not in name), fallback)

    @property
    def consensus_pool(self) -> tuple[str, ...]:
        return self.trusted_models or self.available_models


class _AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=2, max_length=200)
    goal: str = Field(min_length=5, max_length=2000)
    backstory: str = Field(default="", max_length=4000)
    model: str = ""
    tool_ids: list[str] = Field(default_factory=list, max_length=20)
    skill_ids: list[str] = Field(default_factory=list, max_length=12)
    output_fields: dict[str, Literal["string", "integer", "number", "boolean"]] = Field(default_factory=dict, max_length=24)


class _TaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=5, max_length=4000)
    expected_output: str = Field(min_length=5, max_length=1000)
    output_fields: dict[str, Literal["string", "integer", "number", "boolean"]] = Field(default_factory=dict, max_length=24)


class _StageDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["crew", "sandbox", "approval"]
    label: str = Field(min_length=2, max_length=160)
    purpose: str = Field(min_length=5, max_length=2000)
    agents: list[_AgentDraft] = Field(default_factory=list, max_length=8)
    tasks: list[_TaskDraft] = Field(default_factory=list, max_length=12)
    model: str = ""
    tool_ids: list[str] = Field(default_factory=list, max_length=20)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=8)
    coder_instructions: str = Field(default="", max_length=4000)
    reviewer_instructions: str = Field(default="", max_length=3000)
    requires_approval: bool = False
    consensus: bool = False


class _WorkflowDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=10, max_length=2000)
    stages: list[_StageDraft] = Field(min_length=1, max_length=12)
    design_reasoning: list[str] = Field(default_factory=list, max_length=12)


class _BotDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=5, max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    routine_name: str = Field(min_length=2, max_length=160)
    routine_markdown: str = Field(min_length=20, max_length=8000)
    design_reasoning: list[str] = Field(default_factory=list, max_length=8)


class _StudioDraft(BaseModel):
    """Project-specific direction layered over a studio blueprint's fixed structure."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=10, max_length=2000)
    direction: str = Field(default="", max_length=3000)
    objectives: dict[str, str] = Field(default_factory=dict, max_length=24)
    design_reasoning: list[str] = Field(default_factory=list, max_length=12)


RigorRequest = Literal["minimal", "standard", "full_studio", "auto", "solo", "units"]
_FRONTIER_MODEL_HINTS = ("opus", "sonnet", "gpt-5", "gpt-4.1", "gemini-2.5-pro", "gemini-3-pro", "o3", "o4")
JsonGenerator = Callable[[str, type[BaseModel]], Awaitable[Any]]
_DraftT = TypeVar("_DraftT", bound=BaseModel)
Validator = Callable[[WorkflowSpec], WorkflowSpec]


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip().lower()).strip("_")
    return (cleaned or fallback)[:72]


def _schema_document(name: str, fields: Mapping[str, str]) -> dict[str, Any]:
    safe_fields = fields or {"summary": "string", "confidence": "number"}
    return {
        "title": name,
        "type": "object",
        "additionalProperties": False,
        "properties": {key: {"type": value} for key, value in safe_fields.items()},
        "required": list(safe_fields),
    }


def _with_web_sandbox_tools(spec: WorkflowSpec, context: ArchitectWorkspaceContext, prompt: str) -> WorkflowSpec:
    if not any(term in prompt.casefold() for term in ("html", "website", "webgl", "frontend", "browser", "trình duyệt", "three.js")):
        return spec
    available = {tool.id for tool in context.mcp_tools} | set(context.builtin_tool_ids)
    web_tools = tuple(tool for tool in ("browser_automation", "start_background_process", "get_process_logs") if tool in available)
    nodes = tuple(node.model_copy(update={"tool_ids": tuple(dict.fromkeys((*node.tool_ids, *web_tools)))}) if isinstance(node, NexusGenSandboxNodeSpec) else node for node in spec.nodes)
    return spec.model_copy(update={"nodes": nodes})


class MetaArchitectService:
    """Generate graphs through model-proposed structure and deterministic validation."""

    def __init__(self, json_generator: JsonGenerator, validator: Validator | None = None) -> None:
        self._generate_json = json_generator
        self._validator = validator or self._validate_graph

    async def _draft(self, prompt: str, schema: type[_DraftT]) -> _DraftT:
        """Ask for a draft; when it breaks the schema, show the model its own errors and ask again (2 repairs)."""
        problem = ""
        last_error: ValidationError | None = None
        for _ in range(3):
            asked = prompt if not problem else (
                f"{prompt}\n\nYour previous JSON was rejected by validation:\n{problem}\n"
                "Return the full corrected JSON only, with exactly the documented fields."
            )
            try:
                return schema.model_validate(await self._generate_json(asked, schema))
            except ValidationError as error:
                problem = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()[:8])
                last_error = error
        assert last_error is not None
        raise last_error

    @staticmethod
    def _validate_graph(spec: WorkflowSpec) -> WorkflowSpec:
        if not isinstance(spec, WorkflowSpec):
            raise TypeError("Architect output must be a WorkflowSpec")
        outgoing: dict[str, list[str]] = {node.id: [] for node in spec.nodes}
        for edge in spec.edges:
            if not edge.loop_back:
                outgoing[edge.source].append(edge.target)
        start = next(node.id for node in spec.nodes if node.kind == "start")
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Generated workflow contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in outgoing[node_id]:
                walk(target)
            visiting.remove(node_id)
            visited.add(node_id)

        walk(start)
        if visited != set(outgoing):
            raise ValueError("Generated workflow contains an unreachable node")
        return spec

    async def generate_workflow(
        self,
        user_requirement_prompt: str,
        workspace_context: ArchitectWorkspaceContext,
        *,
        existing_workflow_spec: WorkflowSpec | None = None,
        preferred_model: str | None = None,
        budget_tier: str | None = None,
        workflow_id: UUID | None = None,
        version: int = 1,
        rigor: RigorRequest | None = None,
        studio_id: str | None = None,
        input_file_names: Sequence[str] = (),
    ) -> tuple[WorkflowSpec, dict[str, Any]]:
        prompt = user_requirement_prompt.strip()
        if not prompt or len(prompt) > 12_000:
            raise ValueError("Requirement prompt must contain 1 to 12,000 characters")
        if studio_id is not None and studio_id not in STUDIO_BY_ID:
            raise ValueError(f"Unknown studio: {studio_id}")
        studio = (STUDIO_BY_ID[studio_id] if studio_id else detect_studio(prompt)) if existing_workflow_spec is None else None
        effective: RigorRequest = rigor or ("full_studio" if studio is not None else "minimal")
        level_note: dict[str, str] = {}
        if effective == "units" and existing_workflow_spec is None:
            return await self._generate_units(prompt, workspace_context, workflow_id=workflow_id or uuid4(), version=version, preferred_model=preferred_model)
        if effective in ("auto", "solo") and existing_workflow_spec is None:
            if effective == "auto" and studio is not None and not (studio.domain == "software" and assess(prompt, input_file_names).level == "solo" and is_small_script_request(prompt)):
                effective = "full_studio"
            else:
                assessment = Assessment("solo", "a single coder and reviewer was requested") if effective == "solo" else assess(prompt, input_file_names)
                if assessment.level == "solo":
                    return self._generate_solo(prompt, workspace_context, assessment, workflow_id=workflow_id or uuid4(), version=version, preferred_model=preferred_model)
                effective = "minimal"
                level_note = {"level": "team", "level_reason": assessment.reason}
        elif effective in ("auto", "solo", "units"):
            effective = "minimal"
        if effective != "minimal" and existing_workflow_spec is None:
            return await self._generate_studio(
                prompt, workspace_context, studio or _fallback_studio(prompt), effective,
                workflow_id=workflow_id or uuid4(), version=version, preferred_model=preferred_model,
            )
        if existing_workflow_spec is not None and (
            existing_workflow_spec.tenant_id != workspace_context.tenant_id
            or existing_workflow_spec.workspace_id != workspace_context.workspace_id
        ):
            raise ValueError("Existing workflow scope differs from architect workspace")
        payload = {
            "requirement": prompt,
            "workspace_context": workspace_context.model_dump(mode="json"),
            "existing_workflow_spec": existing_workflow_spec.model_dump(mode="json") if existing_workflow_spec else None,
            "preferred_model": preferred_model,
            "budget_tier": budget_tier,
            "constraints": {
                "stage_types": ["crew", "sandbox", "approval"],
                "models": list(workspace_context.available_models),
                "mcp_tools": [tool.model_dump(mode="json") for tool in workspace_context.mcp_tools],
                "knowledge_bases": [kb.model_dump(mode="json") for kb in workspace_context.knowledge_bases],
                "output_schema_names": list(workspace_context.output_schema_names),
            },
        }
        draft = await self._draft(
            "Decompose the goal into a short ordered executable workflow. Use crew for tool-backed production and review, sandbox for code or calculations, and approval before sensitive actions. When the user asks to create media, include a production Crew task that actually calls media_generation and report_exporter and returns real artifact filenames; a plan alone is incomplete. Use only listed models, tools, and knowledge bases. Give every Crew agent tailored role, goal and backstory and each task a compact JSON output_fields map. Return JSON only.\n" +
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            _WorkflowDraft,
        )
        spec = self._assemble(draft, prompt, workspace_context, workflow_id or (existing_workflow_spec.id if existing_workflow_spec else uuid4()),
                              (existing_workflow_spec.version + 1 if existing_workflow_spec else version), preferred_model)
        validated = self._validator(spec)
        summary = {
            "summary": draft.summary,
            "design_reasoning": draft.design_reasoning,
            "agents": [{"id": agent.id, "role": agent.role, "model": agent.model, "tools": list(agent.tool_ids),
                        "knowledge_capsules": [str(value) for value in agent.knowledge_capsule_ids]}
                       for node in validated.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents],
            "tools": sorted({tool_id for node in validated.nodes if isinstance(node, CrewNodeSpec)
                             for agent in node.agents for tool_id in agent.tool_ids}),
            "knowledge_capsules": sorted({str(capsule_id) for node in validated.nodes if isinstance(node, CrewNodeSpec)
                                           for agent in node.agents for capsule_id in agent.knowledge_capsule_ids}),
            **level_note,
        }
        return validated, summary

    async def _generate_units(
        self,
        prompt: str,
        context: ArchitectWorkspaceContext,
        *,
        workflow_id: UUID,
        version: int,
        preferred_model: str | None,
    ) -> tuple[WorkflowSpec, dict[str, Any]]:
        models = context.available_models
        model = preferred_model if preferred_model in models else context.fallback_model
        draft = await self._draft(
            "Split this request into independent units that different people could build separately, then one integration step. "
            f"Use {MIN_UNITS} to {MAX_UNITS} units. Write `contract`: the exact module and file names, function and class signatures, "
            "data formats and error types every unit relies on, precise enough that a unit can be built and tested without seeing the others. "
            "Give every unit the files only it owns in `owned_paths` (relative paths, no test files, no file owned twice) and its instructions. "
            "If the request cannot be split like this, still return the best split you can. Return JSON only.\n" + json.dumps({"requirement": prompt}, ensure_ascii=False),
            UnitsDraft,
        )
        strong = context.frontier_model(model)
        spec = self._validator(build_units_workflow(
            draft, workflow_id=workflow_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id, version=version,
            unit_model=model, integrate_model=strong,
        ))
        sandboxes = [node for node in spec.nodes if isinstance(node, NexusGenSandboxNodeSpec)]
        agents = [
            {"id": f"{node.id}_{part}", "role": f"{node.label} · {part}", "model": node.coder_model if part == "coder" else node.reviewer_model,
             "tools": list(node.tool_ids), "knowledge_capsules": []}
            for node in sandboxes for part in ("coder", "reviewer")
        ]
        summary = {
            "summary": draft.summary, "design_reasoning": draft.design_reasoning, "agents": agents, "tools": [], "knowledge_capsules": [],
            "agent_count": len(agents), "level": "units",
            "level_reason": f"{len(draft.units)} units that each own separate files, then one integration step",
        }
        return spec, summary

    def _generate_solo(
        self,
        prompt: str,
        context: ArchitectWorkspaceContext,
        assessment: Assessment,
        *,
        workflow_id: UUID,
        version: int,
        preferred_model: str | None,
    ) -> tuple[WorkflowSpec, dict[str, Any]]:
        models = context.available_models
        model = preferred_model if preferred_model in models else context.fallback_model
        repair_model = context.frontier_model(model)
        title = " ".join(prompt.split())[:70]
        spec = self._validator(_with_web_sandbox_tools(build_solo_workflow(
            workflow_id=workflow_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id, version=version,
            name=f"Code task: {title}", model=model, repair_model=repair_model,
        ), context, prompt))
        agents = [
            {"id": f"{node.id}_{part}", "role": f"{node.label} · {part}", "model": node.coder_model if part == "coder" else node.reviewer_model,
             "tools": [], "knowledge_capsules": []}
            for node in spec.nodes if isinstance(node, NexusGenSandboxNodeSpec) for part in ("coder", "reviewer")
        ]
        summary = {
            "summary": "One coder and reviewer work in a sandbox until the checks pass; a repair attempt on the strongest model runs only if they do not.",
            "design_reasoning": [assessment.reason], "agents": agents, "tools": sorted({tool for node in spec.nodes if isinstance(node, NexusGenSandboxNodeSpec) for tool in node.tool_ids}), "knowledge_capsules": [],
            "agent_count": 2, "level": "solo", "level_reason": assessment.reason,
        }
        return spec, summary

    async def _generate_studio(
        self,
        prompt: str,
        context: ArchitectWorkspaceContext,
        blueprint: StudioBlueprint,
        rigor: RigorRequest,
        *,
        workflow_id: UUID,
        version: int,
        preferred_model: str | None,
    ) -> tuple[WorkflowSpec, dict[str, Any]]:
        studio_rigor: Literal["standard", "full_studio"] = "full_studio" if rigor == "full_studio" else "standard"
        models = context.available_models
        default_model = preferred_model if preferred_model in models else context.fallback_model
        director_model = preferred_model if preferred_model in models else context.frontier_model(default_model)
        probe = build_studio_graph(blueprint, studio_rigor, model=default_model, director_model=director_model)
        department_keys = [item["id"] for item in probe.departments if item["id"] != "direction"]
        draft = await self._draft(
            "Adapt a production studio to the user's request. Keep it short. Return JSON only with: name, summary, "
            "direction (the creative or product vision in 2-4 sentences), objectives (a map from department id to one "
            "or two sentences of project-specific direction for that department), design_reasoning (up to 5 bullets). "
            f"Studio: {blueprint.title}. Department ids: {json.dumps(department_keys)}.\nRequest: {prompt}",
            _StudioDraft,
        )
        objectives = {key: value for key, value in draft.objectives.items() if key in department_keys}
        objectives["direction"] = draft.direction
        tools = {tool.id for tool in context.mcp_tools} | set(context.builtin_tool_ids)
        graph = build_studio_graph(
            blueprint, studio_rigor, model=default_model, director_model=director_model,
            tools=tools, objectives=objectives, requirement=prompt,
        )
        spec = self._validator(_with_web_sandbox_tools(WorkflowSpec(
            id=workflow_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id, name=draft.name,
            version=version, nodes=tuple(graph.nodes), edges=tuple(graph.edges), layout=graph.layout, modes=graph.modes,
        ), context, prompt))
        agents: list[dict[str, Any]] = [
            {"id": agent.id, "role": agent.role, "tier": agent.tier, "model": agent.model, "tools": list(agent.tool_ids), "knowledge_capsules": []}
            for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents
        ]
        for node in spec.nodes:
            if isinstance(node, NexusGenSandboxNodeSpec):
                agents.extend({"id": f"{node.id}_{part}", "role": f"{node.label} · {part}", "tier": "specialist",
                               "model": node.coder_model if part == "coder" else node.reviewer_model, "tools": list(node.tool_ids),
                               "knowledge_capsules": []} for part in ("coder", "reviewer"))
        summary = {
            "summary": draft.summary, "design_reasoning": draft.design_reasoning, "rigor": studio_rigor,
            "studio": blueprint.id, "agent_count": graph.agent_count, "departments": graph.departments,
            "agents": agents,
            "tools": sorted({tool_id for item in agents for tool_id in item["tools"]}),
            "knowledge_capsules": [],
        }
        return spec, summary

    def _assemble(
        self,
        draft: _WorkflowDraft,
        prompt: str,
        context: ArchitectWorkspaceContext,
        workflow_id: UUID,
        version: int,
        preferred_model: str | None,
    ) -> WorkflowSpec:
        nodes: list[Any] = [StartNodeSpec(id="start", label="Start from request", input_schema={"type": "object"})]
        edges: list[WorkflowEdgeSpec] = []
        learning_edges: list[LearningEdgeSpec] = []
        layout: dict[str, NodePosition] = {"start": NodePosition(x=80, y=180)}
        previous = "start"
        previous_learning_agent: str | None = None
        available_models = context.available_models
        default_model = preferred_model if preferred_model in available_models else context.fallback_model
        tool_ids = {tool.id for tool in context.mcp_tools} | set(context.builtin_tool_ids)
        builtin_tool_ids = set(context.builtin_tool_ids)
        capsule_candidates = list(context.verified_capsules)
        kb_by_id = {kb.id: kb for kb in context.knowledge_bases}
        stage_count = 0
        risky_prompt = bool(re.search(r"\b(email|e-mail|send|delete|destructive|payment|purchase|external|publish|customer)\b", prompt, re.I))
        # Exclusions such as "không tạo ảnh/video" must not add a mandatory media task.
        positive_request = re.sub(
            r"\b(?:do\s+not|don['’]t|never|without|no|not|không|đừng)\b[^.!?;\n]*?"
            r"(?=[.!?;\n]|,\s*(?:but\s+|nhưng\s+)?(?:create|generate|produce|make|render|tạo|làm|sản xuất)\b|$)",
            "", prompt, flags=re.I,
        )
        requested_media = "video" if re.search(r"\b(video|clip|mp4|phim)\b", positive_request, re.I) else "audio" if re.search(r"\b(audio|voice|speech|mp3|giọng)\b", positive_request, re.I) else "image" if re.search(r"\b(image|photo|picture|ảnh|hình)\b", positive_request, re.I) else None
        production_requested = requested_media is not None and bool(re.search(r"\b(create|generate|produce|make|render|tạo|làm|sản xuất)\b", positive_request, re.I))
        final_crew_index = max((index for index, item in enumerate(draft.stages) if item.kind == "crew"), default=-1)

        for stage_index, stage in enumerate(draft.stages):
            action_text = f"{stage.label} {stage.purpose} " + " ".join(task.description for task in stage.tasks)
            needs_gate = stage.requires_approval or (risky_prompt and bool(re.search(
                r"\b(publish|post|send|email|purchase|payment|delete|customer)\b", action_text, re.I,
            )))
            if needs_gate and stage.kind != "approval":
                gate_id = f"approval_before_{stage_index + 1}"
                nodes.append(ApprovalGateNodeSpec(
                    id=gate_id, label="Approve action", action_description=f"Approve before {stage.label}: {stage.purpose}",
                    required_role="admin", boundary_rules=("external_action", "high_spend"),
                ))
                edges.append(WorkflowEdgeSpec(source=previous, target=gate_id))
                stage_count += 1
                layout[gate_id] = NodePosition(x=80 + stage_count * 330, y=180)
                previous = gate_id
            selected_kbs = [kb_id for kb_id in stage.knowledge_base_ids if kb_id in kb_by_id]
            if not selected_kbs:
                matched = sorted(
                    context.knowledge_bases,
                    key=lambda kb: _overlap(f"{prompt} {stage.purpose}", kb.name), reverse=True,
                )
                if matched and _overlap(f"{prompt} {stage.purpose}", matched[0].name) > 0:
                    selected_kbs = [matched[0].id]
                elif len(matched) == 1:
                    selected_kbs = [matched[0].id]
            for kb_id in selected_kbs[:2]:
                rag_id = f"knowledge_{stage_index + 1}_{stage_count + 1}"
                nodes.append(RAGNodeSpec(
                    id=rag_id, label=f"Retrieve {kb_by_id[kb_id].name}", knowledge_base_id=kb_id,
                    query_template="{input}", top_k=5,
                ))
                edges.append(WorkflowEdgeSpec(source=previous, target=rag_id))
                stage_count += 1
                layout[rag_id] = NodePosition(x=80 + stage_count * 330, y=180)
                previous = rag_id

            node_id = f"{stage.kind}_{stage_index + 1}"
            x = 80 + (stage_count + 1) * 330
            if stage.kind == "crew":
                agent_drafts = stage.agents or [_AgentDraft(role=stage.label, goal=stage.purpose, backstory="A careful specialist that follows the task schema.", model=stage.model or default_model)]
                agents: list[AgentSpec] = []
                tasks: list[TaskSpec] = []
                for agent_index, agent in enumerate(agent_drafts):
                    agent_id = f"{node_id}_agent_{agent_index + 1}"
                    requested_tools = [item for item in (*stage.tool_ids, *agent.tool_ids) if item in tool_ids]
                    chosen_tools = _select_tools(f"{agent.role} {agent.goal} {stage.purpose}", context.mcp_tools, requested_tools)
                    assigned_task = stage.tasks[min(agent_index, len(stage.tasks) - 1)].description if stage.tasks else ""
                    text_for_skills = f"{agent.role} {agent.goal} {stage.purpose} {assigned_task}"
                    text_for_skills = text_for_skills.lower()
                    skill_rules = dict(context.skill_keywords)
                    skill_ids = [slug for slug, terms in skill_rules.items() if slug in context.skill_slugs and any(term.lower() in text_for_skills for term in terms)][:3]
                    tool_rules = {
                        "web_search": ("web", "search", "research", "news"), "web_scraper": ("web", "page", "scrape"),
                        "document_parser": ("document", "file", "csv", "pdf", "excel"), "chart_generator": ("chart", "plot", "visual", "forecast"),
                        "safe_sql": ("sql", "database", "query", "table"), "report_exporter": ("report", "export", "document"),
                        "knowledge_rag": ("knowledge", "policy", "internal", "document"),
                        "media_generation": ("image", "photo", "audio", "voiceover", "video", "veo", "grok"),
                        "sandbox_shell": ("ffmpeg", "render", "edit video", "subtitle"),
                        "http_webhook": ("publish", "post campaign", "send campaign", "webhook"),
                        "browser_automation": ("publish", "social media", "browser"),
                    }
                    if any(term in text_for_skills for term in ("image", "photo", "audio", "voiceover", "video")):
                        chosen_tools.extend(tool for tool in ("media_generation", "report_exporter") if tool in builtin_tool_ids)
                    if "marketing" in text_for_skills:
                        chosen_tools.extend(tool for tool in ("web_search", "report_exporter") if tool in builtin_tool_ids)
                    chosen_tools.extend(tool_id for tool_id, terms in tool_rules.items() if tool_id in builtin_tool_ids and any(term in text_for_skills for term in terms))
                    chosen_tools = list(dict.fromkeys(chosen_tools))
                    capsule_refs = _select_capsules(f"{agent.role} {agent.goal} {stage.purpose}", capsule_candidates)
                    model = agent.model if agent.model in available_models else (stage.model if stage.model in available_models else default_model)
                    agents.append(AgentSpec(
                        id=agent_id, role=agent.role, goal=agent.goal, backstory=agent.backstory or agent.role,
                        model=model, tool_ids=tuple(chosen_tools), knowledge_capsule_ids=tuple(item.capsule.capsule_id for item in capsule_refs),
                        skill_ids=tuple(skill_ids),
                    ))
                if previous_learning_agent and agents:
                    learning_edges.append(LearningEdgeSpec(
                        source_agent_id=previous_learning_agent,
                        target_agent_id=agents[0].id,
                        scope=PropagationScope.WORKFLOW_SCOPED,
                        allow_heuristics=True,
                        allow_code_patterns=False,
                        require_human_approval=True,
                    ))
                previous_learning_agent = agents[-1].id
                task_drafts = stage.tasks or [_TaskDraft(description=stage.purpose, expected_output="Return a validated structured result.", output_fields={"summary": "string", "confidence": "number"})]
                for task_index, task in enumerate(task_drafts):
                    assigned = agents[min(task_index, len(agents) - 1)]
                    schema_name = f"Architect_{_slug(node_id, 'stage')}_{task_index + 1}Output"
                    fields = task.output_fields or (agent_drafts[min(task_index, len(agent_drafts) - 1)].output_fields)
                    schema_json = _schema_document(schema_name, fields)
                    tasks.append(TaskSpec(
                        id=f"{node_id}_task_{task_index + 1}", agent_id=assigned.id,
                        description=task.description, expected_output=task.expected_output,
                        output_schema=schema_name, output_schema_json=schema_json,
                        expected_artifact_paths=tuple(deliverables_in(task.description)),
                    ))
                if production_requested and stage_index == final_crew_index and "media_generation" in builtin_tool_ids:
                    producer = agents[-1]
                    if "media_generation" not in producer.tool_ids:
                        agents[-1] = producer.model_copy(update={"tool_ids": tuple(dict.fromkeys((*producer.tool_ids, "media_generation", "report_exporter")))})
                    output_name = f"Architect_{_slug(node_id, 'stage')}_DeliverableOutput"
                    tasks.append(TaskSpec(
                        id=f"{node_id}_deliverable", agent_id=producer.id,
                        description=f"Produce the actual {requested_media} deliverable now using media_generation with kind={requested_media}. Use the original user request and prior task results to form the prompt. Call report_exporter to save a script or production report. Return the exact filenames returned by both tools. Do not invent paths or claim success without both tool results.",
                        expected_output=f"A real {requested_media} file and a Markdown production report, both saved as run artifacts.",
                        output_schema=output_name,
                        output_schema_json=_schema_document(output_name, {"artifact_filename": "string", "report_filename": "string", "summary": "string"}),
                        context_task_ids=tuple(item.id for item in tasks),
                    ))
                consensus = stage.consensus or bool(re.search(r"\b(finance|financial|legal|medical|high[- ]stakes)\b", stage.purpose, re.I))
                consensus_models = tuple(dict.fromkeys(context.consensus_pool[:2]))
                consensus_models = consensus_models if len(consensus_models) >= 2 else ()
                from nexus_core_schema.models import ConsensusConfigSpec
                consensus_config = ConsensusConfigSpec(
                    enabled=consensus and len(consensus_models) >= 2,
                    models=consensus_models if consensus and len(consensus_models) >= 2 else (),
                    arbiter_model=default_model if consensus and len(consensus_models) >= 2 else "",
                )
                nodes.append(CrewNodeSpec(id=node_id, label=stage.label, agents=tuple(agents), tasks=tuple(tasks), consensus_config=consensus_config))
            elif stage.kind == "sandbox":
                sandbox_text = f"{stage.label} {stage.purpose} {stage.coder_instructions} {prompt}".lower()
                sandbox_skill_rules = dict(context.skill_keywords)
                sandbox_skills = [slug for slug, terms in sandbox_skill_rules.items() if slug in context.skill_slugs and any(term.lower() in sandbox_text for term in terms)][:3]
                inferred_tools = tuple(tool_id for tool_id in ("sandbox_shell", "document_parser", "chart_generator") if tool_id in builtin_tool_ids and any(term in sandbox_text for term in {
                    "sandbox_shell": ("shell", "python", "code", "command"),
                    "document_parser": ("csv", "document", "file", "excel"),
                    "chart_generator": ("chart", "plot", "visualization"),
                }[tool_id]))
                web_tools = ("browser_automation", "start_background_process", "get_process_logs") if any(term in sandbox_text for term in ("html", "website", "webgl", "frontend", "browser", "trình duyệt", "three.js")) else ()
                sandbox_tools = tuple(dict.fromkeys(tool for tool in (*stage.tool_ids, *inferred_tools, *web_tools) if tool in tool_ids))
                nodes.append(NexusGenSandboxNodeSpec(
                    id=node_id, label=stage.label, coder_model=stage.model if stage.model in available_models else default_model,
                    reviewer_model=stage.model if stage.model in available_models else default_model,
                    coder_instructions=stage.coder_instructions or stage.purpose,
                    reviewer_instructions=stage.reviewer_instructions or "Check correctness, safety and verification output.",
                    sandbox_provider="docker", max_rounds=10, timeout_seconds=600,
                    verification_command="python -m compileall .",
                    skill_ids=tuple(sandbox_skills), tool_ids=sandbox_tools,
                ))
                previous_learning_agent = f"{node_id}_coder"
            else:
                nodes.append(ApprovalGateNodeSpec(
                    id=node_id, label=stage.label, action_description=stage.purpose,
                    required_role="admin", boundary_rules=("external_action",),
                ))
            edges.append(WorkflowEdgeSpec(source=previous, target=node_id))
            stage_count += 1
            layout[node_id] = NodePosition(x=x, y=180)
            previous = node_id
        if existing_layout := set(layout) ^ {node.id for node in nodes}:
            raise ValueError(f"Layout construction failed: {sorted(existing_layout)}")
        return WorkflowSpec(
            id=workflow_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=draft.name, version=version, nodes=tuple(nodes), edges=tuple(edges),
            learning_edges=tuple(learning_edges), layout=layout,
        )

    async def generate_bot(
        self,
        user_requirement_prompt: str,
        workspace_context: ArchitectWorkspaceContext,
        *,
        timezone: str = "UTC",
        cron_expression: str = "0 9 * * 1-5",
        bot_id: UUID | None = None,
        preferred_model: str | None = None,
    ) -> tuple[PersistentBotSpec, MarkdownRoutineSpec, list[str]]:
        prompt = user_requirement_prompt.strip()
        if not prompt or len(prompt) > 12_000:
            raise ValueError("Bot job description must contain 1 to 12,000 characters")
        draft = await self._draft(
            "Design one persistent teammate and a useful scheduled markdown routine. Choose only an available model. Return JSON only.\n" +
            json.dumps({"job_description": prompt, "models": list(workspace_context.available_models),
                        "preferred_model": preferred_model, "timezone": timezone,
                        "cron_expression": cron_expression}, ensure_ascii=False), _BotDraft,
        )
        if preferred_model is not None:
            if preferred_model not in workspace_context.available_models:
                raise ValueError("Preferred bot model is not available in this workspace")
            draft = draft.model_copy(update={"model": preferred_model})
        if draft.model not in workspace_context.available_models:
            raise ValueError("Generated bot model is not available in this workspace")
        identifier = bot_id or uuid4()
        routine_id = uuid4()
        bot = PersistentBotSpec(
            id=identifier, tenant_id=workspace_context.tenant_id, workspace_id=workspace_context.workspace_id,
            name=draft.name, description=draft.description, model=draft.model,
            tool_ids=tuple(tool for tool in (
                "peer_workflow", "web_search", "document_parser", "report_exporter", "media_generation", "knowledge_rag",
            ) if tool in workspace_context.builtin_tool_ids),
            memory_namespace=f"bot:{identifier}", routine_ids=(routine_id,),
        )
        routine = MarkdownRoutineSpec(
            id=routine_id, bot_id=identifier, tenant_id=workspace_context.tenant_id,
            workspace_id=workspace_context.workspace_id, name=draft.routine_name,
            instruction_markdown=draft.routine_markdown, cron_expression=cron_expression,
            timezone=timezone, enabled=True,
        )
        return bot, routine, draft.design_reasoning


def _fallback_studio(prompt: str) -> StudioBlueprint:
    """Studio for an explicit rigor request whose domain is unclear: reports and analyses use the software factory."""
    del prompt
    return next(blueprint for blueprint in STUDIO_BLUEPRINTS if blueprint.domain == "software")


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9+#.-]{2,}", value.casefold()) if token not in {"with", "from", "that", "this", "the", "and", "for"}}


def _overlap(left: str, right: str) -> float:
    first, second = _tokens(left), _tokens(right)
    return len(first & second) / max(1, len(first | second))


def _select_tools(task: str, tools: Sequence[ToolDescriptor], explicit: Sequence[str]) -> list[str]:
    selected = set(explicit)
    scored = sorted(((_overlap(task, f"{tool.name} {tool.description}"), tool.id) for tool in tools), reverse=True)
    selected.update(tool_id for score, tool_id in scored if score >= 0.12)
    return sorted(selected)


def _select_capsules(task: str, capsules: Sequence[VerifiedCapsuleDescriptor]) -> list[VerifiedCapsuleDescriptor]:
    scored: list[tuple[float, VerifiedCapsuleDescriptor]] = []
    for entry in capsules:
        capsule = entry.capsule
        compatibility = _overlap(task, " ".join((*capsule.source_domain_tags, capsule.trigger_preconditions, capsule.distilled_heuristic)))
        score = compatibility * 0.7 + entry.impact_score * 0.3
        if compatibility > 0:
            scored.append((score, entry))
    return [entry for _, entry in sorted(scored, key=lambda pair: pair[0], reverse=True)[:3]]
