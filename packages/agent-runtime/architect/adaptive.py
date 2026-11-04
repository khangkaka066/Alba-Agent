"""Light path for code and calculation requests: one sandbox team, no architect call, and a fixed escalation.

A request that plainly asks for code or a calculation does not need a planned team: a coder and reviewer pair with
executable verification handles it, and skipping the architect call saves its latency and cost. When that attempt
does not verify, a router sends the same request to a repair attempt on the strongest available model that is told
why the first one failed. Everything else (research, media, outward actions, knowledge bases) keeps the planned team.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from nexus_core_schema.models import (
    NexusGenSandboxNodeSpec,
    NodePosition,
    RouteSpec,
    RouterNodeSpec,
    StartNodeSpec,
    WorkflowEdgeSpec,
    WorkflowSpec,
)

Level = Literal["solo", "team"]

_CODE = re.compile(
    r"\b(python|code|function|class|method|module|package|script|unit ?tests?|test suite|bug|fix|refactor|implement|"
    r"algorithm|parse|parser|regex|csv|json|sql|calculate|compute|api endpoint|lập trình|hàm|lỗi|sửa lỗi|tính toán)\b|"
    r"`[\w./-]+\.(?:py|js|ts|go|rs|java|c|cpp)`|\.py\b",
    re.IGNORECASE,
)
_NEEDS_PLANNED_TEAM = re.compile(
    r"\b(image|photo|picture|video|clip|audio|voice|speech|mp3|mp4|web ?site research|search the web|scrape|news|"
    r"email|e-mail|send|publish|post to|payment|purchase|customer|knowledge base|marketing|campaign|brand|"
    r"ảnh|hình|phim|giọng|gửi|đăng|thanh toán)\b",
    re.IGNORECASE,
)

SOLO_INSTRUCTIONS = (
    "Complete the request exactly as written, working only on the files in the working directory. Before the first "
    "execution, list every behavioural clause the request or the docstrings state. Fix root causes, not the "
    "symptoms the shipped tests happen to show, and add a check for any clause those tests do not cover. Do not "
    "finish until the verification command passes."
)
ESCALATION_INSTRUCTIONS = (
    "A first attempt at this request did not pass verification; its summary and the reason are in "
    "completed_node_outputs. Start from the original files. Re-read the request and every docstring, write down each "
    "behavioural clause, and find which one the first attempt got wrong before changing anything. Cover each clause "
    "with a check, and do not finish until the verification command passes."
)


@dataclass(frozen=True, slots=True)
class Assessment:
    level: Level
    reason: str


def assess(prompt: str, input_file_names: Sequence[str] = ()) -> Assessment:
    """Pick the light path only for a request that is plainly code or a calculation and needs nothing outside the sandbox."""
    needs = _NEEDS_PLANNED_TEAM.search(prompt)
    if needs:
        return Assessment("team", f"the request mentions '{needs.group(0).lower()}', which a code sandbox alone cannot deliver")
    if any(name.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp")) for name in input_file_names):
        return Assessment("solo", "source files were supplied, so this is a code task for one coder and reviewer")
    code = _CODE.search(prompt)
    if code:
        return Assessment("solo", f"the request is about code ('{code.group(0).lower()}'), so one coder and reviewer is enough")
    return Assessment("team", "the request does not clearly ask for code, so a planned team is used")


def strong_model(available: Sequence[str], fallback: str, hints: Sequence[str]) -> str:
    """The first available frontier-class model for the repair attempt, or the fallback when none is listed."""
    return next((name for name in available if any(hint in name for hint in hints) and "mini" not in name), fallback)


def build_solo_workflow(
    *, workflow_id: UUID, tenant_id: UUID, workspace_id: UUID, version: int, name: str, model: str, repair_model: str,
) -> WorkflowSpec:
    """start -> solo -> gate; the gate ends the run when solo verified and otherwise runs one repair attempt."""
    nodes = (
        StartNodeSpec(id="start", label="Start from request", input_schema={"type": "object"}),
        NexusGenSandboxNodeSpec(
            id="solo", label="Code and verify", coder_model=model, reviewer_model=model,
            coder_instructions=SOLO_INSTRUCTIONS, reviewer_instructions="Check correctness against every clause of the request and the verification output.",
            max_rounds=10, timeout_seconds=600, verification_command="python -m compileall .", on_failure="continue",
        ),
        RouterNodeSpec(
            id="gate", label="Verified?",
            routes=(RouteSpec(name="verified", field_path="solo.exit_code", operator="eq", value=0),),
            default_route="escalate",
        ),
        NexusGenSandboxNodeSpec(
            id="repair", label="Repair with evidence", coder_model=repair_model, reviewer_model=repair_model,
            coder_instructions=ESCALATION_INSTRUCTIONS,
            reviewer_instructions="Check each clause of the request against the verification output before approving.",
            max_rounds=14, timeout_seconds=900, verification_command="python -m compileall .",
        ),
    )
    edges = (
        WorkflowEdgeSpec(source="start", target="solo"),
        WorkflowEdgeSpec(source="solo", target="gate"),
        WorkflowEdgeSpec(source="gate", target="repair", route="escalate"),
    )
    layout = {
        "start": NodePosition(x=80, y=180), "solo": NodePosition(x=410, y=180),
        "gate": NodePosition(x=740, y=180), "repair": NodePosition(x=1070, y=180),
    }
    return WorkflowSpec(
        id=workflow_id, tenant_id=tenant_id, workspace_id=workspace_id, name=name, version=version,
        nodes=nodes, edges=edges, layout=layout,
    )
