"""Units team: independent units built against one written contract, then integrated.

Splitting only pays when the pieces really are independent. The planner therefore has to name, for every unit, the files
it alone owns, and write the interface contract all units share; a plan whose owned paths overlap, or that has fewer than
three units, is rejected here and the model is shown why. Each unit runs as its own coder/reviewer sandbox with executable
self-tests, and one integration node (which waits for all of them) mounts their files, wires them together and must add
integration tests of its own before the result counts as verified.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus_core_schema.models import (
    ARTIFACT_PATH_PATTERN,
    NexusGenSandboxNodeSpec,
    NodePosition,
    StartNodeSpec,
    WorkflowEdgeSpec,
    WorkflowSpec,
)

MIN_UNITS = 3
MAX_UNITS = 8
_UNIT_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_PATH = re.compile(ARTIFACT_PATH_PATTERN)


class UnitDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=31)
    label: str = Field(min_length=2, max_length=120)
    instructions: str = Field(min_length=10, max_length=3000)
    owned_paths: list[str] = Field(min_length=1, max_length=6)


class UnitsDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=10, max_length=2000)
    contract: str = Field(min_length=30, max_length=6000)
    units: list[UnitDraft] = Field(min_length=1, max_length=MAX_UNITS + 4)
    integration_instructions: str = Field(default="", max_length=3000)
    design_reasoning: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def units_are_independent(self) -> UnitsDraft:
        problems = unit_problems(self.units)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def test_path(unit_id: str) -> str:
    return f"test_{unit_id}.py"


def unit_problems(units: Sequence[UnitDraft]) -> list[str]:
    """Why these units cannot be built independently, or an empty list when they can."""
    problems: list[str] = []
    if not MIN_UNITS <= len(units) <= MAX_UNITS:
        problems.append(f"a units plan needs {MIN_UNITS} to {MAX_UNITS} independent units, not {len(units)}")
    ids = [unit.id for unit in units]
    for unit_id in ids:
        if not _UNIT_ID.match(unit_id):
            problems.append(f"unit id '{unit_id}' must be lowercase letters, digits and underscores")
    if len(set(ids)) != len(ids):
        problems.append("unit ids must be unique")
    owner: dict[str, str] = {}
    reserved = {test_path(unit_id) for unit_id in ids}
    for unit in units:
        for path in unit.owned_paths:
            if not _PATH.match(path) or path.startswith("test_") or path.rsplit("/", 1)[-1].startswith("test_"):
                problems.append(f"'{path}' is not a valid owned path (relative, no test_ prefix; each unit's test file is added for it)")
            elif path in reserved:
                problems.append(f"'{path}' collides with a unit's test file")
            elif path in owner:
                problems.append(f"'{path}' is owned by both '{owner[path]}' and '{unit.id}'; every file needs exactly one owner")
            else:
                owner[path] = unit.id
    owned = sorted(owner)
    for first in owned:
        for second in owned:
            if first != second and second.startswith(first.rstrip("/") + "/"):
                problems.append(f"'{first}' and '{second}' overlap ({owner[first]} / {owner[second]}); a folder and a file inside it cannot have different owners")
    return problems


UNIT_RULES = (
    "Other units are being built at the same time by other people against the same contract, so build only your unit and "
    "follow the contract's names and signatures exactly. Write only the files you own and your own test file; do not create "
    "stand-ins for other units' modules. Test your unit against the contract with unittest, using small fakes for anything "
    "another unit provides."
)
INTEGRATION_RULES = (
    "The units' delivered files and their tests are already in the working directory (see files_from_earlier_nodes). Wire them "
    "together, run every test, and when two units disagree, fix the module that violates the contract rather than the "
    "contract or the unit tests. Add at least two integration tests of your own that exercise the pieces together."
)


def build_units_workflow(
    draft: UnitsDraft, *, workflow_id: UUID, tenant_id: UUID, workspace_id: UUID, version: int, unit_model: str, integrate_model: str,
) -> WorkflowSpec:
    """start -> every unit -> integrate (waits for all).

    The graph fans out, but the runner currently executes the nodes of one run one at a time: they share one container, one working
    directory and one execution lock. Running units at the same time needs a per-node working directory first.
    """
    nodes: list[object] = [StartNodeSpec(id="start", label="Start from request", input_schema={"type": "object"})]
    edges: list[WorkflowEdgeSpec] = []
    layout: dict[str, NodePosition] = {"start": NodePosition(x=80, y=40 + 90 * (len(draft.units) // 2))}
    unit_ids: list[str] = []
    for index, unit in enumerate(draft.units):
        node_id = f"unit_{unit.id}"
        unit_ids.append(node_id)
        owned = (*unit.owned_paths, test_path(unit.id))
        nodes.append(NexusGenSandboxNodeSpec(
            id=node_id, label=unit.label, coder_model=unit_model, reviewer_model=unit_model,
            coder_instructions=f"{draft.contract}\n\nYOUR UNIT: {unit.label}\n{unit.instructions}\n\nFiles you own: {', '.join(owned)}.\n{UNIT_RULES}",
            reviewer_instructions="Check the unit against the contract's names, signatures and error cases, and against the test results.",
            max_rounds=10, timeout_seconds=600, verification_command="python -m compileall .",
            on_unverified="fail", expected_artifact_paths=owned,
        ))
        edges.append(WorkflowEdgeSpec(source="start", target=node_id))
        edges.append(WorkflowEdgeSpec(source=node_id, target="integrate"))
        layout[node_id] = NodePosition(x=410, y=40 + 180 * index)
    nodes.append(NexusGenSandboxNodeSpec(
        id="integrate", label="Integrate and verify", coder_model=integrate_model, reviewer_model=integrate_model,
        coder_instructions=f"{draft.contract}\n\n{draft.integration_instructions}\n\n{INTEGRATION_RULES}".strip(),
        reviewer_instructions="Approve only when every unit test and your integration tests pass and the pieces work together as the contract describes.",
        max_rounds=14, timeout_seconds=900, verification_command="python -m compileall .",
        join="all", mount_artifacts_from=tuple(unit_ids), min_added_tests=2,
    ))
    layout["integrate"] = NodePosition(x=740, y=40 + 90 * (len(draft.units) // 2))
    return WorkflowSpec(
        id=workflow_id, tenant_id=tenant_id, workspace_id=workspace_id, name=draft.name, version=version,
        nodes=tuple(nodes), edges=tuple(edges), layout=layout,  # type: ignore[arg-type]
    )
