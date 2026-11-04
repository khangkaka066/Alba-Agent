"""Durable, typed state shared by every compiled node."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID
    run_id: UUID
    workflow_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    status: Literal["queued", "running", "paused", "completed", "failed"] = "queued"
    sequence: int = Field(default=0, ge=0)
    input_data: dict[str, Any] = Field(default_factory=dict)
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    # Files handed over by an earlier team in this workspace: name, source run, path inside this run, size, mime type and an excerpt.
    upstream_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    # Sandbox nodes whose result was delivered without executable proof; their files live under `unverified/`.
    unverified_nodes: list[str] = Field(default_factory=list)
    active_node_id: str | None = None
    pending_approval_id: UUID | None = None
    pending_boundary: dict[str, str] | None = None
