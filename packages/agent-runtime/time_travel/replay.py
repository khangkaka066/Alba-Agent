"""Pure state transformations used by scoped replay/fork endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from flows.state import WorkflowState


@dataclass(frozen=True)
class ReplayBranch:
    run_id: UUID
    branch_name: str
    state: WorkflowState
    node_overrides: dict[str, Any]


def rewind_state(historical: WorkflowState, *, run_id: UUID | None = None,
                 mutated_state: dict[str, Any] | None = None,
                 node_overrides: dict[str, Any] | None = None) -> ReplayBranch:
    if node_overrides and any(key not in {"prompt", "model", "temperature"} for key in node_overrides):
        raise ValueError("Unsupported replay override")
    snapshot = historical.model_copy(deep=True)
    if mutated_state:
        if set(mutated_state) - {"input_data", "node_outputs"}:
            raise ValueError("Only input_data and node_outputs may be edited during replay")
        if "input_data" in mutated_state:
            if not isinstance(mutated_state["input_data"], dict):
                raise ValueError("Replay input_data must be an object")
            snapshot.input_data = dict(mutated_state["input_data"])
        if "node_outputs" in mutated_state:
            if not isinstance(mutated_state["node_outputs"], dict):
                raise ValueError("Replay node_outputs must be an object")
            snapshot.node_outputs = dict(mutated_state["node_outputs"])
    snapshot.run_id = run_id or uuid4()
    snapshot.id = snapshot.run_id
    snapshot.status = "running"
    snapshot.pending_approval_id = None
    snapshot.pending_boundary = None
    snapshot.active_node_id = None
    return ReplayBranch(snapshot.run_id, "Replay", snapshot, dict(node_overrides or {}))


def fork_state(historical: WorkflowState, branch_a: dict[str, Any], branch_b: dict[str, Any]) -> tuple[ReplayBranch, ReplayBranch]:
    a = rewind_state(historical, node_overrides=branch_a)
    b = rewind_state(historical, node_overrides=branch_b)
    return ReplayBranch(a.run_id, "Branch A", a.state, a.node_overrides), ReplayBranch(b.run_id, "Branch B", b.state, b.node_overrides)
