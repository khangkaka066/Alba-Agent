"""Workspace-scoped skills registry and native tool catalog/playground."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.context import TenantContext, require_role
from app.models import AgentSkill, AuditLog, KnowledgeBase, KnowledgeCapsule, TransferApplicationLog, TransferCircuitBreaker, Workflow, WorkspaceBuiltinTool
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from nexus_builtin_tools import BuiltinToolRegistry, TOOLS, ToolContext
from agent_skills import SkillLoader, SkillSpec
from learning_transfer.negative_transfer_detector import DetectorConfig, TransferObservation, score_transfer_pair

router = APIRouter(tags=["skills-and-tools"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    trigger_keywords: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    recommended_models: tuple[str, ...] = ()
    body: str = Field(min_length=40, max_length=100_000)

    def markdown(self) -> str:
        return SkillSpec.model_validate(self.model_dump()).to_markdown()


class SkillImport(BaseModel):
    content: str = Field(min_length=50, max_length=110_000)


class ToolToggle(BaseModel):
    enabled: bool


class ToolPlayground(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class SkillAttach(BaseModel):
    workflow_id: UUID
    node_id: str
    agent_id: str
    skill_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()


class CapsulePromotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capsule_id: UUID
    slug: str = Field(min_length=1, max_length=120)


def _catalog() -> SkillLoader:
    return SkillLoader()


# Request-scoped services are supplied in route handlers; keeping helper arguments explicit avoids global state.
def _skill_response(skill: SkillSpec, *, builtin: bool, customized: bool = False) -> dict[str, Any]:
    return {**skill.model_dump(exclude={"body"}), "builtin": builtin, "customized": customized, "content": skill.to_markdown()}


@router.get("/api/v1/skills")
async def list_skills(context: READ, services: Any = Depends(get_services)) -> list[dict[str, Any]]:
    loader = _catalog()
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(AgentSkill))).all()
    overrides = {row.slug: row for row in rows}
    result: list[dict[str, Any]] = []
    for skill in loader._skills.values():
        row = overrides.get(skill.slug)
        current = SkillSpec.from_markdown(row.content) if row else skill
        result.append(_skill_response(current, builtin=True, customized=row is not None))
    builtin_slugs = set(loader._skills)
    result.extend(_skill_response(SkillSpec.from_markdown(row.content), builtin=False) for row in rows if row.slug not in builtin_slugs)
    return result


@router.post("/api/v1/skills", status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    skill = SkillSpec.model_validate({**payload.model_dump(), "body": payload.body})
    if skill.slug in _catalog()._skills:
        raise HTTPException(status.HTTP_409_CONFLICT, "Built-in skills can be customized with PUT")
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if await session.scalar(select(AgentSkill).where(AgentSkill.slug == skill.slug)):
            raise HTTPException(status.HTTP_409_CONFLICT, "A skill with this slug already exists")
        row = AgentSkill(tenant_id=context.tenant_id, workspace_id=context.workspace_id, slug=skill.slug, name=skill.name, category=skill.category, description=skill.description, content=skill.to_markdown(), builtin=False)
        session.add(row)
    return _skill_response(skill, builtin=False)


@router.put("/api/v1/skills/{slug}")
async def update_skill(slug: str, payload: SkillCreate, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    if payload.slug != slug: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Path and body slugs must match")
    skill = SkillSpec.model_validate({**payload.model_dump(), "body": payload.body})
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(AgentSkill).where(AgentSkill.slug == slug).with_for_update())
        if row is None:
            row = AgentSkill(tenant_id=context.tenant_id, workspace_id=context.workspace_id, slug=slug, name=skill.name, category=skill.category, description=skill.description, content=skill.to_markdown(), builtin=False)
            session.add(row)
        else:
            row.name, row.category, row.description, row.content = skill.name, skill.category, skill.description, skill.to_markdown()
    return _skill_response(skill, builtin=slug in _catalog()._skills, customized=True)


@router.post("/api/v1/skills/import", status_code=status.HTTP_201_CREATED)
async def import_skill(payload: SkillImport, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    try: skill = SkillSpec.from_markdown(payload.content)
    except Exception as error: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid SKILL.md: {error}") from error
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(AgentSkill).where(AgentSkill.slug == skill.slug).with_for_update())
        if row is None:
            row = AgentSkill(tenant_id=context.tenant_id, workspace_id=context.workspace_id, slug=skill.slug, name=skill.name, category=skill.category, description=skill.description, content=skill.to_markdown(), builtin=False); session.add(row)
        else: row.name, row.category, row.description, row.content = skill.name, skill.category, skill.description, skill.to_markdown()
    return _skill_response(skill, builtin=skill.slug in _catalog()._skills, customized=True)


@router.get("/api/v1/skills/{slug}/export", response_class=PlainTextResponse)
async def export_skill(slug: str, context: READ, services: Any = Depends(get_services)) -> Response:
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(AgentSkill).where(AgentSkill.slug == slug))
    if row is not None: content = row.content
    else:
        try: content = _catalog().get(slug).to_markdown()
        except LookupError as error: raise not_found("Skill was not found") from error
    return Response(content, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.md"'})


@router.delete("/api/v1/skills/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(slug: str, context: BUILD, services: Any = Depends(get_services)) -> Response:
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(AgentSkill).where(AgentSkill.slug == slug))
        if row is None or row.builtin: raise not_found("Custom skill was not found")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/skills/promote-capsule")
async def promote_capsule(payload: CapsulePromotion, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    config = DetectorConfig(
        threshold=float(os.environ.get("NEXUS_SKILL_PROMOTION_MIN_TIS", "0.15")),
        minimum_applications=int(os.environ.get("NEXUS_SKILL_PROMOTION_MIN_APPLICATIONS", "5")),
    )
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        capsule = await session.scalar(select(KnowledgeCapsule).where(KnowledgeCapsule.capsule_id == payload.capsule_id).with_for_update())
        if capsule is None: raise not_found("Knowledge capsule was not found")
        if capsule.propagation_scope != "WORKSPACE_VERIFIED" or capsule.status != "active":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only active workspace-verified capsules can be promoted")
        logs = (await session.scalars(select(TransferApplicationLog).where(TransferApplicationLog.capsule_id == capsule.id))).all()
        breakers = (await session.scalars(select(TransferCircuitBreaker.target_agent_id).where(TransferCircuitBreaker.capsule_id == capsule.id, TransferCircuitBreaker.active.is_(True)))).all()
        targets = sorted({item.target_agent_id for item in logs})
        scores: list[float] = []
        for target_id in targets:
            target_logs = [item for item in logs if item.target_agent_id == target_id]
            def observation(item: TransferApplicationLog) -> TransferObservation:
                return TransferObservation(item.success, item.retry_and_error_turns, item.human_approval_rejected, item.token_count, item.latency_ms)
            baseline = tuple(observation(item) for item in target_logs if item.condition == "baseline")
            treatment = tuple(observation(item) for item in target_logs if item.condition == "treatment")
            decision = score_transfer_pair(payload.capsule_id, target_id, baseline, treatment, config)
            if decision.sample_count >= config.minimum_applications and not decision.negative_transfer:
                scores.append(decision.impact.score)
        impact = max(scores, default=0.0)
        if breakers or impact < config.threshold:
            raise HTTPException(status.HTTP_409_CONFLICT, "Capsule lacks sufficient positive transfer evidence or has a quarantined target")
        row = await session.scalar(select(AgentSkill).where(AgentSkill.slug == payload.slug).with_for_update())
        if row is not None:
            existing = SkillSpec.from_markdown(row.content)
        else:
            try: existing = _catalog().get(payload.slug)
            except LookupError as error: raise not_found("Target skill was not found") from error
        section = "## Learned Best Practices & Edge Cases"
        addition = f"\n\n### Verified capsule (TIS {impact:.3f})\n\n{capsule.distilled_heuristic}"
        body = existing.body.rstrip() + (addition if section in existing.body else "\n\n" + section + addition) + "\n"
        updated = existing.model_copy(update={"body": body})
        if row is None:
            row = AgentSkill(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id, slug=updated.slug, name=updated.name, category=updated.category, description=updated.description, content=updated.to_markdown(), builtin=True)
            session.add(row)
        else:
            row.name, row.category, row.description, row.content = updated.name, updated.category, updated.description, updated.to_markdown()
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id, action="skill.capsule_promoted", target_type="agent_skill", target_id=row.id, details={"capsule_id": str(payload.capsule_id), "slug": payload.slug, "tis_score": impact}))
    return {"slug": payload.slug, "capsule_id": str(payload.capsule_id), "tis_score": impact, "promoted": True}


@router.post("/api/v1/skills/attach")
async def attach_skill(payload: SkillAttach, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    known = {item.slug for item in _catalog()._skills.values()}
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        workflow = await session.scalar(select(Workflow).where(Workflow.id == payload.workflow_id).with_for_update())
        if workflow is None: raise not_found("Workflow was not found")
        custom = set((await session.scalars(select(AgentSkill.slug))).all())
        if not set(payload.skill_ids) <= known | custom: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown skill selected")
        if not set(payload.tool_ids) <= {item.id for item in TOOLS}: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown built-in tool selected")
        spec = json.loads(json.dumps(workflow.spec))
        node = next((item for item in spec.get("nodes", []) if item.get("id") == payload.node_id), None)
        if node is None: raise not_found("Workflow node was not found")
        if node.get("kind") == "crew":
            agent = next((item for item in node.get("agents", []) if item.get("id") == payload.agent_id), None)
            if agent is None: raise not_found("Agent was not found in this node")
            agent["skill_ids"], agent["tool_ids"] = list(payload.skill_ids), list(payload.tool_ids)
        elif node.get("kind") == "sandbox" and payload.agent_id in {f"{node['id']}_coder", "coder"}:
            node["skill_ids"], node["tool_ids"] = list(payload.skill_ids), list(payload.tool_ids)
        else: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Selected node does not support skills")
        workflow.spec = spec; workflow.version += 1
    return {"workflow_id": str(payload.workflow_id), "version": workflow.version, "skill_ids": payload.skill_ids, "tool_ids": payload.tool_ids}


@router.get("/api/v1/tools/builtin")
async def list_tools(context: READ, services: Any = Depends(get_services)) -> list[dict[str, Any]]:
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = {row.tool_id: row.enabled for row in (await session.scalars(select(WorkspaceBuiltinTool))).all()}
    return [{**item.__dict__, "enabled": rows.get(item.id, True)} for item in TOOLS]


@router.put("/api/v1/tools/builtin/{tool_id}/enabled")
async def toggle_tool(tool_id: str, payload: ToolToggle, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    if tool_id not in {item.id for item in TOOLS}: raise not_found("Built-in tool was not found")
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(WorkspaceBuiltinTool).where(WorkspaceBuiltinTool.tool_id == tool_id).with_for_update())
        if row is None: session.add(WorkspaceBuiltinTool(tenant_id=context.tenant_id, workspace_id=context.workspace_id, tool_id=tool_id, enabled=payload.enabled))
        else: row.enabled = payload.enabled
    return {"tool_id": tool_id, "enabled": payload.enabled}


@router.post("/api/v1/tools/builtin/{tool_id}/test")
async def test_tool(tool_id: str, payload: ToolPlayground, context: BUILD, services: Any = Depends(get_services)) -> dict[str, Any]:
    if tool_id not in {item.id for item in TOOLS}: raise not_found("Built-in tool was not found")
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        config = await session.scalar(select(WorkspaceBuiltinTool).where(WorkspaceBuiltinTool.tool_id == tool_id))
        if config is not None and not config.enabled: raise HTTPException(status.HTTP_403_FORBIDDEN, "This tool is disabled in the workspace")
        kb_id = payload.payload.get("knowledge_base_id")
        if kb_id is not None:
            try: base = await session.get(KnowledgeBase, UUID(str(kb_id)))
            except ValueError as error: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid knowledge base") from error
            if base is None: raise not_found("Knowledge base was not found")
    artifact_root = Path(os.environ.get("NEXUS_ARTIFACT_ROOT", "/tmp/nexus-artifacts")) / str(context.tenant_id) / str(context.workspace_id) / "playground"
    artifact_root.mkdir(parents=True, exist_ok=True)
    async def rag(query: str) -> Any:
        if kb_id is None: raise ValueError("knowledge_base_id is required")
        from nexus_rag_engine import KnowledgeScope
        return await services.rag().retrieve(KnowledgeScope(context.tenant_id, context.workspace_id, UUID(str(kb_id))), query)
    registry = BuiltinToolRegistry(ToolContext(str(context.tenant_id), str(context.workspace_id), "playground", artifact_root, frozenset({tool_id}), rag_query=rag if tool_id == "knowledge_rag" else None))
    try: result = await registry.run(tool_id, payload.payload)
    except (ValueError, PermissionError, RuntimeError, LookupError) as error: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return {"tool_id": tool_id, "result": result}
