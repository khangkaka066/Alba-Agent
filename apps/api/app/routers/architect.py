"""Natural-language workflow and teammate generation endpoints."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Awaitable, Callable, Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app.auth.context import TenantContext, require_role
from app.models import AgentSkill, AuditLog, TaskConversation, KnowledgeBase, KnowledgeCapsule, LearningPolicy, ModelCredential, TransferApplicationLog, TransferCircuitBreaker, Workflow, WorkflowRun
from app.models.scope import scoped_session
from app.handoff import Source, copy_sources, describe_for_architect, resolve_sources
from app.routers.common import get_services
from app.routers.conversations import append_message, start_conversation
from app.routers.providers import PLATFORM_PROVIDERS
from app.routers.workflows import _check_scope, _sync_learning_policies
from bots.runner import cron_matches
from flows.compiler import FlowCompiler
from architect.team_generator import (
    ArchitectWorkspaceContext,
    KnowledgeBaseDescriptor,
    MetaArchitectService,
    ToolDescriptor,
    VerifiedCapsuleDescriptor,
)
from nexus_core_schema.models import (
    KnowledgeCapsuleSpec,
    MarkdownRoutineSpec,
    PersistentBotSpec,
    PropagationScope,
    SensitivityLevel,
    WorkflowSpec,
)
from nexus_model_gateway.router import GatewayRequest, ModelRate, Provider
from nexus_model_gateway.provider_presets import PRESETS
from nexus_builtin_tools import TOOLS
from team_evolution import DYNAMIC_TEAM_TOOL_ID
from agent_skills import SkillLoader, SkillSpec

router = APIRouter(prefix="/api/v1/architect", tags=["architect"])
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]
NON_CHAT_MODELS = frozenset(model.id for preset in PRESETS for model in preset.models if model.kind != "chat")


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    filename: str = Field(min_length=1, max_length=240)


class GenerateWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_requirement_prompt: str = Field(min_length=1, max_length=12_000)
    preferred_model: str | None = Field(default=None, max_length=200)
    budget_tier: Literal["FREE", "PRO", "ENTERPRISE"] | None = None
    auto_run: bool = True
    rigor: Literal["minimal", "standard", "full_studio"] | None = None
    # Text files from a mounted local folder; the sandbox receives them as flat files, so names carry no path.
    input_files: dict[str, str] = Field(default_factory=dict, max_length=64)
    # Continue an existing thread; without it a new conversation is started for this request.
    conversation_id: UUID | None = None
    # Deliverables of earlier tasks in this workspace that the new team starts from (copied into the new run).
    input_artifacts: list[ArtifactRef] = Field(default_factory=list, max_length=20)
    # Build a specific studio instead of detecting one from the request (used by the hand-off buttons).
    studio_id: str | None = Field(default=None, max_length=100)

    @field_validator("input_files")
    @classmethod
    def validate_input_files(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not name or len(name) > 120 or "/" in name or "\\" in name or name.startswith(".") for name in value):
            raise ValueError("Input file names must be plain file names without paths")
        if sum(len(content.encode("utf-8")) for content in value.values()) > 1_000_000:
            raise ValueError("Input files exceed the 1 MB run-input limit")
        return value


class RefineWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_workflow_spec: WorkflowSpec
    edit_instruction: str = Field(min_length=1, max_length=8_000)
    preferred_model: str | None = Field(default=None, max_length=200)
    budget_tier: Literal["FREE", "PRO", "ENTERPRISE"] | None = None


class GenerateBotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_requirement_prompt: str = Field(min_length=1, max_length=12_000)
    preferred_model: str | None = Field(default=None, max_length=200)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    cron_expression: str = Field(default="0 9 * * 1-5", min_length=1, max_length=100)


def _json_object(content: str) -> Any:
    value = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL | re.IGNORECASE)
    if fence:
        value = fence.group(1)
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("Meta-Architect model response was not valid JSON") from error


JSON_ATTEMPTS = 3
JSON_REMINDER = "Your previous reply was not a complete, valid JSON object. Reply again with only the JSON object, nothing before or after it."


async def _json_with_retry(ask: Callable[[str], Awaitable[str]]) -> Any:
    """A model occasionally returns truncated or fenced-wrong JSON; one bad reply must not fail the whole request."""
    reminder = ""
    for attempt in range(JSON_ATTEMPTS):
        try:
            return _json_object(await ask(reminder))
        except ValueError:
            if attempt == JSON_ATTEMPTS - 1:
                raise
            reminder = JSON_REMINDER
    raise AssertionError("unreachable")


NON_CHAT_NAME_PARTS = ("embed", "whisper", "tts", "dall-e", "image", "moderation", "veo", "speech")


def _approved_chat_models(model_names: set[str]) -> tuple[str, ...]:
    """Chat-capable models this workspace can reach; a missing price schedule never excludes a model."""
    approved: list[str] = []
    for full_name in model_names:
        provider, separator, model = full_name.partition("/")
        if separator and provider and model not in NON_CHAT_MODELS and not any(part in model.lower() for part in NON_CHAT_NAME_PARTS):
            approved.append(full_name)
    return tuple(sorted(approved))


async def _workspace_context(request: Request, context: TenantContext, preferred_model: str | None = None) -> ArchitectWorkspaceContext:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        kb_rows = (await session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name))).all()
        credentials = (await session.scalars(select(ModelCredential).where(ModelCredential.status == "connected"))).all()
        skill_rows = (await session.scalars(select(AgentSkill))).all()
        capsule_rows = (await session.scalars(select(KnowledgeCapsule).where(
            KnowledgeCapsule.status == "active",
            KnowledgeCapsule.propagation_scope == PropagationScope.WORKSPACE_VERIFIED.value,
            KnowledgeCapsule.confidence >= 0.8,
        ))).all()
        capsule_ids = [row.capsule_id for row in capsule_rows]
        active_breakers = set((await session.scalars(select(TransferCircuitBreaker.capsule_id).where(
            TransferCircuitBreaker.capsule_id.in_(capsule_ids), TransferCircuitBreaker.active.is_(True),
        ))).all()) if capsule_ids else set()
        score_rows = (await session.execute(select(
            TransferApplicationLog.capsule_id,
            func.avg(TransferApplicationLog.tis_score),
        ).where(
            TransferApplicationLog.capsule_id.in_(capsule_ids),
            TransferApplicationLog.condition == "treatment",
            TransferApplicationLog.tis_score.is_not(None),
        ).group_by(TransferApplicationLog.capsule_id))).all() if capsule_ids else []
    impact_by_capsule = {capsule_id: float(score or 0.0) for capsule_id, score in score_rows}
    verified: list[VerifiedCapsuleDescriptor] = []
    for row in capsule_rows:
        impact = impact_by_capsule.get(row.capsule_id, 0.0)
        if row.capsule_id in active_breakers or impact <= 0:
            continue
        verified.append(VerifiedCapsuleDescriptor(
            capsule=KnowledgeCapsuleSpec(
                tenant_id=row.tenant_id, workspace_id=row.workspace_id, capsule_id=row.capsule_id,
                source_agent_id=row.source_agent_id, source_role=row.source_role,
                source_domain_tags=tuple(row.source_domain_tags), trigger_preconditions=row.trigger_preconditions,
                distilled_heuristic=row.distilled_heuristic, prohibited_contexts=tuple(row.prohibited_contexts),
                propagation_scope=PropagationScope(row.propagation_scope),
                sensitivity_level=SensitivityLevel(row.sensitivity_level),
                source_workflow_id=row.source_workflow_id, source_crew_id=row.source_crew_id,
                confidence=row.confidence,
            ),
            impact_score=min(1.0, impact),
        ))
    model_names = {
        f"{provider}/{model}" for provider, model in services.model_rates
    }
    for credential in credentials:
        for model in credential.available_models:
            model_names.add(f"{credential.provider}/{model}")
    # A model id typed by the user need not be in any list: it is accepted when a provider that can serve it is connected.
    if preferred_model and preferred_model not in model_names:
        reachable = {credential.provider for credential in credentials} | {provider for variable, provider in PLATFORM_PROVIDERS if os.environ.get(variable)}
        if preferred_model.partition("/")[0] in reachable:
            model_names.add(preferred_model)
    tool_map = services.workspace_tools.get((context.tenant_id, context.workspace_id), {})
    tools = tuple(ToolDescriptor(
        id=tool_id,
        name=str(getattr(tool, "name", tool_id)),
        description=str(getattr(tool, "description", "Approved workspace MCP tool")),
        server_id=tool_id.split("_", 2)[1] if tool_id.startswith("nexus_mcp_") else "workspace-tools",
    ) for tool_id, tool in tool_map.items()) + tuple(ToolDescriptor(
        id=item.id, name=item.name, description=item.description, server_id="nexus-builtin",
    ) for item in TOOLS)
    skill_catalog = dict(SkillLoader()._skills)
    skill_catalog.update({row.slug: SkillSpec.from_markdown(row.content) for row in skill_rows})
    return ArchitectWorkspaceContext(
        tenant_id=context.tenant_id, workspace_id=context.workspace_id,
        available_models=_approved_chat_models(model_names), mcp_tools=tools,
        knowledge_bases=tuple(KnowledgeBaseDescriptor(id=row.id, name=row.name) for row in kb_rows),
        verified_capsules=tuple(verified), output_schema_names=tuple(sorted(services.output_schemas)),
        skill_slugs=tuple(skill_catalog),
        skill_keywords={slug: tuple(skill.trigger_keywords) for slug, skill in skill_catalog.items()},
        builtin_tool_ids=(*(item.id for item in TOOLS), DYNAMIC_TEAM_TOOL_ID),
    )


def _service(request: Request, context: TenantContext, workspace: ArchitectWorkspaceContext,
             preferred_model: str | None) -> MetaArchitectService:
    services = get_services(request)
    candidates = _approved_chat_models(set(workspace.available_models))
    configured = preferred_model or os.environ.get("NEXUS_ARCHITECT_MODEL")
    if configured and configured not in candidates:
        source = "Requested" if preferred_model else "Configured"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY if preferred_model else status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{source} model {configured} is not available in this workspace. Connect a provider or subscription that serves it, or choose a connected chat model.")
    model = configured or next((name for name in candidates if name.startswith("openai/")), None) or next(iter(candidates), None)
    if model is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No chat model is connected for the Meta-Architect; connect a subscription plan or API key in Settings")

    async def generate_json(prompt: str, output_model: type[BaseModel]) -> Any:
        provider, separator, model_name = model.partition("/")
        if not separator:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Meta-Architect model has no provider")
        async def ask(reminder: str) -> str:
            messages: list[dict[str, str]] = [{"role": "system", "content": f"Return one JSON object matching this schema: {json.dumps(output_model.model_json_schema(), ensure_ascii=False)}"},
                        {"role": "user", "content": prompt}]
            if reminder:
                messages.append({"role": "user", "content": reminder})
            response = await services.gateway().complete(GatewayRequest(
                tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                provider=cast(Provider, provider), model=model_name, messages=tuple(messages),
                max_input_tokens=24_000, max_output_tokens=8_000,
                billing_mode="platform", agent_name="meta_architect",
            ))
            return response.content

        return await _json_with_retry(ask)

    return MetaArchitectService(generate_json, FlowCompiler.validate)


@router.post("/generate-workflow")
async def generate_workflow(body: GenerateWorkflowRequest, request: Request, context: BUILD) -> dict[str, Any]:
    workspace = await _workspace_context(request, context, body.preferred_model)
    service = _service(request, context, workspace, body.preferred_model)
    sources: list[Source] = []
    if body.input_artifacts:
        async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
            known = set((await session.scalars(select(WorkflowRun.id).where(WorkflowRun.id.in_([item.run_id for item in body.input_artifacts])))).all())
        sources = resolve_sources([(item.run_id, item.filename) for item in body.input_artifacts], context, known)
    try:
        spec, summary = await service.generate_workflow(
            body.user_requirement_prompt + describe_for_architect(sources), workspace, preferred_model=body.preferred_model,
            budget_tier=body.budget_tier, rigor=body.rigor, studio_id=body.studio_id,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    document = spec.model_dump(mode="json")
    if not body.auto_run:
        return {"workflow_spec": document, **summary}
    if context.service_key and "run" not in context.scopes and "admin" not in context.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Service key run scope is required")
    _check_scope(spec, context)
    services = get_services(request)
    run_id = uuid4()
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        session.add(Workflow(
            id=spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=spec.name, version=spec.version, spec=document,
        ))
        upstream = copy_sources(context, sources, run_id) if sources else []
        session.add(WorkflowRun(
            id=run_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            workflow_id=spec.id, status="queued",
            input_data={"task": body.user_requirement_prompt, **({"sandbox_files": body.input_files} if body.input_files else {}),
                        **({"upstream_artifacts": upstream} if upstream else {})},
        ))
        session.add(AuditLog(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            actor_id=context.user_id, action="architect.workflow_run_queued", target_type="workflow_run",
            target_id=run_id, details={"workflow_id": str(spec.id)},
        ))
        await session.flush()
        await _sync_learning_policies(session, spec, context)
        conversation = await session.get(TaskConversation, body.conversation_id) if body.conversation_id else None
        if body.conversation_id and conversation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation is not visible in this workspace")
        if conversation is None:
            conversation = await start_conversation(session, context, body.user_requirement_prompt)
        await append_message(session, conversation, "user", body.user_requirement_prompt,
                             meta={"attachments": [{"run_id": entry["source_run_id"], "filename": entry["source_filename"], "name": entry["name"]} for entry in upstream]} if upstream else None)
        await append_message(session, conversation, "team", str(summary.get("summary") or spec.name), run_id=run_id, workflow_id=spec.id,
                             meta={"agent_count": summary.get("agent_count"), "studio": summary.get("studio")})
        conversation_id = conversation.id
    try:
        await services.dispatcher.workflow(context.tenant_id, context.workspace_id, run_id)
    except Exception as error:
        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            run = await session.get(WorkflowRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.now(timezone.utc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Workflow queue is unavailable") from error
    return {"workflow": document, "workflow_spec": document, "run_id": str(run_id), "conversation_id": str(conversation_id), **summary}


@router.post("/refine-workflow")
async def refine_workflow(body: RefineWorkflowRequest, request: Request, context: BUILD) -> dict[str, Any]:
    current = body.current_workflow_spec
    if (current.tenant_id, current.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Workflow scope differs from authenticated workspace")
    workspace = await _workspace_context(request, context, body.preferred_model)
    service = _service(request, context, workspace, body.preferred_model)
    combined = f"Existing workflow: {current.name}. User change request: {body.edit_instruction}. Preserve existing behavior unless the instruction changes it."
    try:
        updated, summary = await service.generate_workflow(
            body.edit_instruction + "\n" + combined, workspace, existing_workflow_spec=current,
            preferred_model=body.preferred_model,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    before = {node.id: node.model_dump(mode="json") for node in current.nodes}
    after = {node.id: node.model_dump(mode="json") for node in updated.nodes}
    added = [node_id for node_id in after.keys() - before.keys()]
    removed = [node_id for node_id in before.keys() - after.keys()]
    modified = [node_id for node_id in before.keys() & after.keys() if before[node_id] != after[node_id]]
    return {"workflow_spec": updated.model_dump(mode="json"), **summary,
            "structural_diff": {"added_nodes": added, "modified_nodes": modified, "removed_nodes": removed}}


@router.post("/generate-bot")
async def generate_bot(body: GenerateBotRequest, request: Request, context: BUILD) -> dict[str, Any]:
    try:
        ZoneInfo(body.timezone)
        cron_matches(body.cron_expression, datetime.now(timezone.utc), body.timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine timezone or cron expression is invalid") from error
    workspace = await _workspace_context(request, context, body.preferred_model)
    service = _service(request, context, workspace, body.preferred_model)
    try:
        bot, routine, reasoning = await service.generate_bot(
            body.user_requirement_prompt, workspace, timezone=body.timezone,
            cron_expression=body.cron_expression, preferred_model=body.preferred_model,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return {"bot_spec": bot.model_dump(mode="json"), "routine_spec": routine.model_dump(mode="json"),
            "design_reasoning": reasoning}
