"""Validated workflow-template and generated-output contracts."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import NodePosition, WorkflowEdgeSpec, WorkflowModesSpec, WorkflowNode


CanvasPosition = NodePosition


class TemplateRoutineSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    instruction_markdown: str = Field(min_length=1)
    cron_expression: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    approval_kind: Literal["external_email", "destructive_command", "high_spend"] | None = None
    approval_description: str | None = None


class TemplateBotSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    model: str = Field(min_length=1, max_length=200)
    memory_namespace_prefix: str = Field(min_length=1, max_length=100)
    routines: tuple[TemplateRoutineSeed, ...] = ()


class WorkflowTemplate(BaseModel):
    """Portable template source. Tenant and workspace scope are assigned on instantiation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    category: Literal["analytics", "engineering", "research", "operations", "studio"]
    tags: tuple[str, ...] = ()
    required_connections: tuple[str, ...] = ()
    readiness_notes: tuple[str, ...] = ()
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1)
    edges: tuple[WorkflowEdgeSpec, ...] = ()
    layout: dict[str, CanvasPosition]
    modes: WorkflowModesSpec = Field(default_factory=WorkflowModesSpec)
    knowledge_base_name: str | None = Field(default=None, max_length=200)
    bot: TemplateBotSeed | None = None

    @model_validator(mode="after")
    def validate_layout_and_graph(self) -> WorkflowTemplate:
        node_ids = {node.id for node in self.nodes}
        if set(self.layout) != node_ids:
            raise ValueError("Template layout must position every workflow node exactly once")
        if self.bot is not None and not self.bot.routines:
            raise ValueError("A template bot must include at least one routine")
        return self

    def workflow_document(self) -> dict[str, Any]:
        return {
            "name": self.title,
            "version": 1,
            "nodes": [node.model_dump(mode="json") for node in self.nodes],
            "edges": [edge.model_dump(mode="json", exclude_none=True) for edge in self.edges],
            "layout": {key: value.model_dump(mode="json") for key, value in self.layout.items()},
            "modes": self.modes.model_dump(mode="json"),
        }


class TemplateInstantiationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    knowledge_base_id: UUID | None = None
    embedding_model: str = Field(default="openai/text-embedding-3-small", pattern=r"^[a-z0-9_]+/.+$")


class TemplateInstantiationResponse(BaseModel):
    template_id: str
    workflow_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    bot_id: UUID | None = None
    routine_ids: tuple[UUID, ...] = ()
    workflow: dict[str, Any] | None = None
    bot: dict[str, Any] | None = None
    routines: tuple[dict[str, Any], ...] = ()
    required_connections: tuple[str, ...] = ()


class TemplateCatalogEntry(BaseModel):
    """Public, tenant-neutral gallery view of a seeded template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    summary: str
    description: str
    category: str
    tags: tuple[str, ...]
    required_connections: tuple[str, ...]
    readiness_notes: tuple[str, ...]
    workflow: dict[str, Any]
    layout: dict[str, CanvasPosition]
    has_bot: bool
    has_routine: bool
