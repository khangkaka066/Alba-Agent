"""Tenant-scoped catalog and atomic one-click template instantiation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.context import TenantContext, require_role
from app.billing.plans import enforce_creation_quota
from app.models import BotRoutine, KnowledgeBase, PersistentBot, Workflow
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from app.routers.teammates import _register_scope
from nexus_core_schema_templates.catalog import TEMPLATE_BY_ID, TEMPLATES
from nexus_core_schema.models import MarkdownRoutineSpec, PersistentBotSpec, WorkflowSpec
from nexus_core_schema.template_models import (
    TemplateCatalogEntry,
    TemplateInstantiationRequest,
    TemplateInstantiationResponse,
)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


@router.get("", response_model=list[TemplateCatalogEntry])
async def list_templates() -> list[TemplateCatalogEntry]:
    return [
        TemplateCatalogEntry(
            id=template.id,
            title=template.title,
            summary=template.summary,
            description=template.description,
            category=template.category,
            tags=template.tags,
            required_connections=template.required_connections,
            readiness_notes=template.readiness_notes,
            workflow=template.workflow_document(),
            layout=template.layout,
            has_bot=template.bot is not None,
            has_routine=bool(template.bot and template.bot.routines),
        )
        for template in TEMPLATES
    ]


@router.post(
    "/{template_id}/instantiate",
    response_model=TemplateInstantiationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def instantiate_template(
    template_id: str,
    body: TemplateInstantiationRequest,
    request: Request,
    context: BUILD,
) -> TemplateInstantiationResponse:
    template = TEMPLATE_BY_ID.get(template_id)
    if template is None:
        raise not_found("Template does not exist")

    services = get_services(request)
    if template.bot is not None:
        await enforce_creation_quota(services.engine, context.tenant_id, context.workspace_id, "bot")
    workflow_id = uuid4()
    knowledge_base_id: UUID | None = None
    if template.knowledge_base_name:
        knowledge_base_id = body.knowledge_base_id or uuid4()

    if knowledge_base_id is not None and body.knowledge_base_id is not None:
        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            existing = await session.get(KnowledgeBase, knowledge_base_id)
            if existing is None:
                raise not_found("Selected knowledge base is not visible in this workspace")

    nodes = tuple(
        node.model_copy(update={"knowledge_base_id": knowledge_base_id})
        if node.kind == "rag" and knowledge_base_id is not None else node
        for node in template.nodes
    )
    workflow = WorkflowSpec(
        id=workflow_id,
        tenant_id=context.tenant_id,
        workspace_id=context.workspace_id,
        name=body.name or template.title,
        version=1,
        nodes=nodes,
        edges=template.edges,
        layout=template.layout,
        modes=template.modes,
    )

    bot_spec: PersistentBotSpec | None = None
    routine_specs: list[MarkdownRoutineSpec] = []
    if template.bot is not None:
        bot_id = uuid4()
        routine_ids = tuple(uuid4() for _ in template.bot.routines)
        bot_spec = PersistentBotSpec(
            id=bot_id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            name=template.bot.name,
            description=template.bot.description,
            model=template.bot.model,
            memory_namespace=f"{template.bot.memory_namespace_prefix}:{context.tenant_id}:{context.workspace_id}:{bot_id}",
            routine_ids=routine_ids,
        )
        for routine_seed, routine_id in zip(template.bot.routines, routine_ids, strict=True):
            instruction = routine_seed.instruction_markdown
            if routine_seed.approval_kind is not None:
                description = routine_seed.approval_description or "Review the proposed routine action."
                instruction = (
                    "---\napproval:\n"
                    f"  kind: {routine_seed.approval_kind}\n"
                    f"  description: {description!r}\n"
                    "---\n\n"
                    + instruction
                )
            routine_specs.append(MarkdownRoutineSpec(
                id=routine_id,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                bot_id=bot_id,
                name=routine_seed.name,
                instruction_markdown=instruction,
                cron_expression=routine_seed.cron_expression,
                timezone=routine_seed.timezone,
                enabled=True,
                workflow_id=workflow.id,
            ))

    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if template.knowledge_base_name and knowledge_base_id is not None and body.knowledge_base_id is None:
            session.add(KnowledgeBase(
                id=knowledge_base_id,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                name=template.knowledge_base_name,
                embedding_model=body.embedding_model,
            ))
        session.add(Workflow(
            id=workflow.id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            name=workflow.name,
            version=workflow.version,
            spec=workflow.model_dump(mode="json"),
        ))
        # No ORM relationships exist, so flush parents before children to satisfy scoped FKs.
        await session.flush()
        if bot_spec is not None:
            session.add(PersistentBot(
                id=bot_spec.id,
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
                name=bot_spec.name,
                model=bot_spec.model,
                spec=bot_spec.model_dump(mode="json"),
            ))
            await session.flush()
            for routine in routine_specs:
                session.add(BotRoutine(
                    id=routine.id,
                    tenant_id=context.tenant_id,
                    workspace_id=context.workspace_id,
                    bot_id=routine.bot_id,
                    name=routine.name,
                    instruction_markdown=routine.instruction_markdown,
                    cron_expression=routine.cron_expression,
                    timezone=routine.timezone,
                    enabled=routine.enabled,
                    workflow_id=routine.workflow_id,
                    interval_seconds=None,
                    allowed_actions=[],
                ))

    if routine_specs:
        await _register_scope(request, context)

    return TemplateInstantiationResponse(
        template_id=template.id,
        workflow_id=workflow.id,
        knowledge_base_id=knowledge_base_id,
        bot_id=bot_spec.id if bot_spec is not None else None,
        routine_ids=tuple(routine.id for routine in routine_specs),
        workflow=workflow.model_dump(mode="json"),
        bot=bot_spec.model_dump(mode="json") if bot_spec is not None else None,
        routines=tuple(routine.model_dump(mode="json") for routine in routine_specs),
        required_connections=template.required_connections,
    )
