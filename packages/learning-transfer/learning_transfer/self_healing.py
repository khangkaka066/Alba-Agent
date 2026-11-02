"""Auditable prompt patches distilled from human review corrections."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import re
from typing import Any


@dataclass(frozen=True)
class PromptPatchProposal:
    before: str
    after: str
    rationale: str
    unified_diff: str = ""
    target_field: str = "task_description"
    knowledge_capsule: dict[str, Any] | None = None


def propose_prompt_patch(before: str, corrected: str, rationale: str) -> PromptPatchProposal:
    if not before.strip() or not corrected.strip() or not rationale.strip():
        raise ValueError("Prompt patches require before, corrected output, and rationale")
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), corrected.splitlines(keepends=True),
        fromfile="a/prompt", tofile="b/prompt",
    ))
    return PromptPatchProposal(before=before, after=corrected, rationale=rationale, unified_diff=diff)


@dataclass(frozen=True)
class CorrectionAnalysis:
    original_ai_output: str
    human_corrected_output: str
    reviewer_comment: str
    output_diff: str
    proposal: PromptPatchProposal


class SelfHealingOptimizer:
    """Turns a human correction into a reviewable, field-scoped prompt patch."""

    _SECRET = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+")

    def analyze(
        self,
        original_ai_output: str,
        human_corrected_output: str,
        reviewer_comment: str,
        *,
        target_field: str = "task_description",
        agent_id: str = "reviewed-agent",
    ) -> CorrectionAnalysis:
        if target_field not in {"goal", "backstory", "task_description", "guardrails"}:
            raise ValueError("Unsupported prompt patch target")
        original = original_ai_output.strip()
        corrected = human_corrected_output.strip()
        comment = reviewer_comment.strip()
        if not original or not corrected or original == corrected:
            raise ValueError("A non-empty, changed human correction is required")
        if len(comment) < 3:
            raise ValueError("Reviewer feedback must explain the correction")
        # Prompt patches should encode reusable instructions, not the reviewed output itself.
        guidance = f"When handling this task, {comment.rstrip('.')} . Validate the result against the requested requirements before returning it."
        guidance = self._SECRET.sub("[REDACTED]", guidance)
        proposal = PromptPatchProposal(
            before=original,
            after=guidance,
            rationale=comment,
            unified_diff="".join(difflib.unified_diff(
                original.splitlines(keepends=True), guidance.splitlines(keepends=True),
                fromfile=f"a/{target_field}", tofile=f"b/{target_field}",
            )),
            target_field=target_field,
        )
        output_diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True), corrected.splitlines(keepends=True),
            fromfile="a/original_output", tofile="b/human_corrected_output",
        ))
        capsule = {
            "source_agent_id": agent_id,
            "source_role": "Human-reviewed agent correction",
            "source_domain_tags": ["human-feedback", target_field],
            "trigger_preconditions": "A similar task with the same reviewer correction context",
            "distilled_heuristic": guidance,
            "prohibited_contexts": ["different task domains", "raw customer data"],
            "propagation_scope": "WORKSPACE_QUARANTINE",
            "sensitivity_level": "CONFIDENTIAL_PII_STRIPPED",
        }
        return CorrectionAnalysis(original, corrected, comment, output_diff,
                                  PromptPatchProposal(**{**proposal.__dict__, "knowledge_capsule": capsule}))
