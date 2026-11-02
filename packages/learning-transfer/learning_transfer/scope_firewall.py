"""Deterministic propagation policy, redaction, and task-compatibility gate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from nexus_core_schema.models import KnowledgeCapsuleSpec, PropagationScope

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|nx-sk)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(?:customer[_ -]?(?:name|id)?|client[_ -]?(?:name|id)?|account[_ -]?(?:number|id)|address|ssn)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(?:customer|client|contact|person)\s+(?:name\s+)?(?:is\s+)?[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+?\d[\d .()/-]{7,}\d)\b"),
)


def _redact(value: str, sensitive_values: tuple[str, ...]) -> str:
    cleaned = value
    for secret in sorted((item for item in sensitive_values if len(item) >= 3), key=len, reverse=True):
        cleaned = re.sub(re.escape(secret), "[REDACTED]", cleaned, flags=re.IGNORECASE)
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def sanitize_capsule(capsule: KnowledgeCapsuleSpec, sensitive_values: tuple[str, ...] = ()) -> KnowledgeCapsuleSpec:
    """Redact common credentials/PII and explicit tenant values before wider sharing."""
    return capsule.model_copy(update={
        "trigger_preconditions": _redact(capsule.trigger_preconditions, sensitive_values),
        "distilled_heuristic": _redact(capsule.distilled_heuristic, sensitive_values),
        "source_domain_tags": tuple(_redact(tag, sensitive_values) for tag in capsule.source_domain_tags),
        "prohibited_contexts": tuple(_redact(item, sensitive_values) for item in capsule.prohibited_contexts),
    })


@dataclass(frozen=True)
class AgentLearningContext:
    agent_id: str
    domain_tags: tuple[str, ...]
    task_description: str
    tenant_id: UUID
    workspace_id: UUID
    crew_id: str | None = None
    workflow_id: str | None = None


@dataclass(frozen=True)
class LearningPolicy:
    source_agent_id: str
    target_agent_id: str
    scope: PropagationScope
    allow_heuristics: bool = True
    allow_code_patterns: bool = False
    require_human_approval: bool = False
    allowed: bool = True


@dataclass(frozen=True)
class FirewallDecision:
    allowed: bool
    reason: str
    capsule: KnowledgeCapsuleSpec | None = None
    compatibility: float = 0.0
    requires_approval: bool = False


class ScopeFirewall:
    def __init__(self, top_k: int = 3, minimum_compatibility: float = 0.08) -> None:
        if top_k < 1 or not 0 <= minimum_compatibility <= 1:
            raise ValueError("Invalid firewall ranking configuration")
        self.top_k = top_k
        self.minimum_compatibility = minimum_compatibility

    @staticmethod
    def _compatibility(capsule: KnowledgeCapsuleSpec, target: AgentLearningContext) -> float:
        source = {tag.casefold() for tag in capsule.source_domain_tags}
        target_tags = {tag.casefold() for tag in target.domain_tags}
        task_terms = set(re.findall(r"[a-z0-9_+#.-]+", target.task_description.casefold()))
        precondition_terms = set(re.findall(r"[a-z0-9_+#.-]+", capsule.trigger_preconditions.casefold()))
        task_overlap = len(task_terms & precondition_terms) / max(1, len(task_terms | precondition_terms))
        tag_overlap = len(source & target_tags) / max(1, len(source | target_tags))
        return min(1.0, tag_overlap * 0.8 + task_overlap * 0.2)

    def authorize(
        self,
        capsule: KnowledgeCapsuleSpec,
        target: AgentLearningContext,
        policy: LearningPolicy | None,
        *,
        same_crew: bool = False,
        same_workflow: bool = False,
        approved: bool = False,
        sensitive_values: tuple[str, ...] = (),
    ) -> FirewallDecision:
        if capsule.tenant_id != target.tenant_id or capsule.workspace_id != target.workspace_id:
            return FirewallDecision(False, "tenant boundary mismatch")
        if target.agent_id in capsule.prohibited_contexts or set(target.domain_tags).intersection(capsule.prohibited_contexts):
            return FirewallDecision(False, "target is explicitly prohibited")
        if capsule.propagation_scope == PropagationScope.AGENT_PRIVATE and target.agent_id != capsule.source_agent_id:
            return FirewallDecision(False, "capsule is agent-private")
        if capsule.propagation_scope == PropagationScope.CREW_LOCAL and not same_crew:
            return FirewallDecision(False, "capsule is restricted to its source crew")
        if capsule.propagation_scope == PropagationScope.WORKFLOW_SCOPED and not same_workflow:
            return FirewallDecision(False, "capsule is restricted to its source workflow")
        if policy is None or not policy.allowed:
            return FirewallDecision(False, "no allowed learning edge is configured")
        if (policy.source_agent_id, policy.target_agent_id) != (capsule.source_agent_id, target.agent_id):
            return FirewallDecision(False, "learning edge does not match capsule and target")
        if capsule.propagation_scope not in (policy.scope, PropagationScope.AGENT_PRIVATE):
            return FirewallDecision(False, "policy scope does not permit this capsule")
        if policy.require_human_approval and not approved:
            return FirewallDecision(False, "human approval is required", requires_approval=True)
        if capsule.propagation_scope == PropagationScope.WORKSPACE_QUARANTINE and not approved:
            return FirewallDecision(False, "quarantined workspace capsules require explicit approval", requires_approval=True)
        has_code_pattern = "```" in capsule.distilled_heuristic or bool(re.search(r"(?m)^\s*(?:def |class |import |from |#!/|\$\s)", capsule.distilled_heuristic))
        if has_code_pattern and not policy.allow_code_patterns:
            return FirewallDecision(False, "policy disallows code patterns")
        if not has_code_pattern and not policy.allow_heuristics:
            return FirewallDecision(False, "policy disallows heuristics")
        score = self._compatibility(capsule, target)
        if score < self.minimum_compatibility:
            return FirewallDecision(False, "target task is not domain-compatible", compatibility=score)
        sanitized = sanitize_capsule(capsule, sensitive_values) if capsule.propagation_scope != PropagationScope.AGENT_PRIVATE else capsule
        return FirewallDecision(True, "propagation allowed", sanitized, score, policy.require_human_approval)

    def select(
        self,
        candidates: tuple[tuple[KnowledgeCapsuleSpec, LearningPolicy | None], ...],
        target: AgentLearningContext,
        *,
        same_crew: bool = False,
        same_workflow: bool = False,
        approved: bool = False,
        sensitive_values: tuple[str, ...] = (),
    ) -> tuple[FirewallDecision, ...]:
        ranked = [self.authorize(capsule, target, policy, same_crew=same_crew,
                                 same_workflow=same_workflow, approved=approved,
                                 sensitive_values=sensitive_values) for capsule, policy in candidates]
        return tuple(sorted((item for item in ranked if item.allowed), key=lambda item: item.compatibility, reverse=True)[: self.top_k])
