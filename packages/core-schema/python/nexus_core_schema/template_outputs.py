"""Structured outputs used by the built-in workflow templates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataAnalysisPlan(StrictOutput):
    objective: str
    metrics: list[str]
    validation_checks: list[str]
    assumptions: list[str]


class DataScienceFindings(StrictOutput):
    summary: str
    statistical_tables: list[dict[str, str | float | int]]
    chart_artifacts: list[str]
    caveats: list[str]


class ExecutiveDataReport(StrictOutput):
    title: str
    executive_summary: str
    key_findings: list[str]
    recommended_actions: list[str]
    limitations: list[str]


class SecurityTestPlan(StrictOutput):
    scope: list[str]
    test_cases: list[str]
    security_checks: list[str]
    exclusions: list[str]


class SecurityAuditReport(StrictOutput):
    summary: str
    findings: list[str]
    tests_executed: list[str]
    unresolved_risks: list[str]


class MarketResearchBrief(StrictOutput):
    market_summary: str
    audience_segments: list[str]
    competitor_observations: list[str]
    source_urls: list[str]
    uncertainties: list[str]


class MarketContentStrategy(StrictOutput):
    positioning: str
    content_pillars: list[str]
    channel_plan: list[str]
    proposed_headlines: list[str]
    citations: list[str]


class CitationReview(StrictOutput):
    verified_claims: list[str]
    unsupported_claims: list[str]
    citation_gaps: list[str]
    publication_ready: bool


class OperationsDigest(StrictOutput):
    digest: str
    high_priority_actions: list[str]
    draft_replies: list[str]
    items_requiring_approval: list[str]


class ApprovalActionPlan(StrictOutput):
    proposed_actions: list[str]
    rationale: str
    requires_human_review: bool = Field(default=True)


BUILTIN_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        DataAnalysisPlan,
        DataScienceFindings,
        ExecutiveDataReport,
        SecurityTestPlan,
        SecurityAuditReport,
        MarketResearchBrief,
        MarketContentStrategy,
        CitationReview,
        OperationsDigest,
        ApprovalActionPlan,
    )
}
