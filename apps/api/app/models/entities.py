"""Workspace-scoped records with composite references that preserve scope."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ScopedRow, scope_constraints, scoped_reference


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="FREE", server_default="FREE")
    billing_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    billing_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_workspaces_tenant_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(ScopedRow, Base):
    __tablename__ = "users"
    __table_args__ = (*scope_constraints("users"), UniqueConstraint("tenant_id", "workspace_id", "email", name="uq_users_scope_email"))

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class WorkspaceMember(ScopedRow, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        *scope_constraints("workspace_members"),
        scoped_reference("workspace_members", "users", "user_id"),
        UniqueConstraint("tenant_id", "workspace_id", "user_id", name="uq_members_scope_user"),
        CheckConstraint("role IN ('owner','admin','builder','viewer')", name="ck_members_role"),
    )

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class ServiceApiKey(ScopedRow, Base):
    __tablename__ = "service_api_keys"
    __table_args__ = (
        *scope_constraints("service_api_keys"),
        scoped_reference("service_api_keys", "users", "created_by_user_id"),
        UniqueConstraint("key_hash", name="uq_service_api_keys_hash"),
        CheckConstraint("key_prefix LIKE 'nx-sk-%'", name="ck_service_api_key_prefix"),
    )

    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersistentBot(ScopedRow, Base):
    __tablename__ = "persistent_bots"
    __table_args__ = scope_constraints("persistent_bots")

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    spec: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class BotRoutine(ScopedRow, Base):
    __tablename__ = "bot_routines"
    __table_args__ = (
        *scope_constraints("bot_routines"),
        scoped_reference("bot_routines", "persistent_bots", "bot_id"),
        scoped_reference("bot_routines", "workflows", "workflow_id"),
        CheckConstraint("interval_seconds IS NULL OR interval_seconds > 0", name="ck_routine_interval_positive"),
    )

    bot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    instruction_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    workflow_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(nullable=True)
    allowed_actions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class BotMessage(ScopedRow, Base):
    __tablename__ = "bot_messages"
    __table_args__ = (
        *scope_constraints("bot_messages"),
        scoped_reference("bot_messages", "persistent_bots", "bot_id"),
        CheckConstraint("role IN ('user','assistant','system')", name="ck_bot_message_role"),
        Index("ix_bot_messages_thread", "tenant_id", "workspace_id", "bot_id", "thread_id", "created_at"),
    )

    bot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class RoutineRun(ScopedRow, Base):
    __tablename__ = "routine_runs"
    __table_args__ = (
        *scope_constraints("routine_runs"),
        scoped_reference("routine_runs", "bot_routines", "routine_id"),
        scoped_reference("routine_runs", "persistent_bots", "bot_id"),
        UniqueConstraint("tenant_id", "workspace_id", "routine_id", "scheduled_for", name="uq_routine_scheduled"),
        CheckConstraint("status IN ('queued','running','paused','completed','failed')", name="ck_routine_run_status"),
    )

    bot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    routine_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    workflow_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class SandboxComputer(ScopedRow, Base):
    __tablename__ = "sandbox_computers"
    __table_args__ = (
        *scope_constraints("sandbox_computers"),
        CheckConstraint("visibility IN ('shared','private')", name="ck_computer_visibility"),
        CheckConstraint("status IN ('provisioning','running','failed','terminated')", name="ck_computer_status"),
        CheckConstraint("visibility = 'shared' OR bot_id IS NOT NULL OR run_id IS NOT NULL", name="ck_private_computer_owner"),
        UniqueConstraint("tenant_id", "workspace_id", "run_id", name="uq_computer_run"),
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    bot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Workflow(ScopedRow, Base):
    __tablename__ = "workflows"
    __table_args__ = (*scope_constraints("workflows"), UniqueConstraint("tenant_id", "workspace_id", "name", "version", name="uq_workflow_scope_version"))

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    spec: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class WorkflowRun(ScopedRow, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        *scope_constraints("workflow_runs"),
        scoped_reference("workflow_runs", "workflows", "workflow_id"),
        CheckConstraint("status IN ('queued','running','paused','completed','failed','cancelled')", name="ck_run_status"),
    )

    workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    input_data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Where and why the run failed (node, agent when known, error type, sanitised message and traceback summary).
    failure: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class TaskConversation(ScopedRow, Base):
    """One chat thread. Follow-up requests start new teams inside the same thread, so a thread can hold several runs."""

    __tablename__ = "task_conversations"
    __table_args__ = scope_constraints("task_conversations")

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConversationMessage(ScopedRow, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        *scope_constraints("conversation_messages"),
        scoped_reference("conversation_messages", "task_conversations", "conversation_id"),
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_message_sequence"),
        CheckConstraint("role IN ('user','team','note')", name="ck_conversation_message_role"),
    )

    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    workflow_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    meta: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)


class RunCheckpoint(ScopedRow, Base):
    __tablename__ = "run_checkpoints"
    __table_args__ = (
        *scope_constraints("run_checkpoints"),
        scoped_reference("run_checkpoints", "workflow_runs", "run_id"),
        UniqueConstraint("tenant_id", "workspace_id", "run_id", "sequence", name="uq_checkpoint_sequence"),
    )

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PromptPatchProposal(ScopedRow, Base):
    __tablename__ = "prompt_patch_proposals"
    __table_args__ = (*scope_constraints("prompt_patch_proposals"), scoped_reference("prompt_patch_proposals", "workflows", "workflow_id"), CheckConstraint("status IN ('pending','applied','dismissed')", name="ck_prompt_patch_status"))

    workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_approval_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_field: Mapped[str] = mapped_column(String(32), nullable=False)
    original_output: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_output: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_comment: Mapped[str] = mapped_column(Text, nullable=False)
    unified_diff: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    applied_workflow_version: Mapped[int | None] = mapped_column(nullable=True)


class GoldenTraceRecord(ScopedRow, Base):
    __tablename__ = "golden_traces"
    __table_args__ = (*scope_constraints("golden_traces"), scoped_reference("golden_traces", "workflow_runs", "run_id"), UniqueConstraint("tenant_id", "workspace_id", "run_id", "agent_id", "task_signature", name="uq_golden_trace_run_agent_task"), Index("ix_golden_trace_task", "tenant_id", "workspace_id", "agent_id", "task_signature"))

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    verified_output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_used: Mapped[str] = mapped_column(String(200), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 8), nullable=False)
    latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)


class DistillationRecommendation(ScopedRow, Base):
    __tablename__ = "distillation_recommendations"
    __table_args__ = (*scope_constraints("distillation_recommendations"), CheckConstraint("status IN ('recommended','applied','rolled_back','rejected')", name="ck_distillation_recommendation_status"))

    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_model: Mapped[str] = mapped_column(String(200), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    few_shot_examples: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="recommended")


class ApprovalRequest(ScopedRow, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        *scope_constraints("approval_requests"),
        scoped_reference("approval_requests", "workflow_runs", "run_id"),
        scoped_reference("approval_requests", "routine_runs", "routine_run_id"),
        CheckConstraint("status IN ('pending','allowed_once','always_allowed','denied')", name="ck_approval_status"),
        CheckConstraint("required_role IN ('owner','admin','builder')", name="ck_approval_required_role"),
        CheckConstraint("(run_id IS NULL) <> (routine_run_id IS NULL)", name="ck_approval_one_run"),
    )

    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    routine_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    required_role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grant_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(ScopedRow, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (*scope_constraints("audit_logs"), Index("ix_audit_scope_created", "tenant_id", "workspace_id", "created_at"))

    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class KnowledgeBase(ScopedRow, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = scope_constraints("knowledge_bases")

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)


class KnowledgeDocument(ScopedRow, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (*scope_constraints("knowledge_documents"), scoped_reference("knowledge_documents", "knowledge_bases", "knowledge_base_id"))

    knowledge_base_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class ModelCredential(ScopedRow, Base):
    __tablename__ = "model_credentials"
    __table_args__ = (*scope_constraints("model_credentials"), UniqueConstraint("tenant_id", "workspace_id", "provider", "name", name="uq_credential_scope_name"))

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(nullable=False)
    preset_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    base_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="untested")
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)
    available_models: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    default_models: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    live_balance: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TenantBudget(Base):
    __tablename__ = "tenant_budgets"
    __table_args__ = (CheckConstraint("remaining_usd >= 0 AND reserved_usd >= 0 AND overage_usd >= 0", name="ck_tenant_budget_nonnegative"),)

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    remaining_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    overage_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal("0"))


class BillingWebhookEvent(ScopedRow, Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        *scope_constraints("billing_webhook_events"),
        UniqueConstraint("tenant_id", "workspace_id", "provider", "event_id", name="uq_billing_event_provider_id"),
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)


class TokenUsageLog(ScopedRow, Base):
    __tablename__ = "token_usage_logs"
    __table_args__ = (
        *scope_constraints("token_usage_logs"),
        CheckConstraint("prompt_tokens >= 0 AND completion_tokens >= 0 AND total_cost_usd >= 0 AND latency_ms >= 0", name="ck_usage_nonnegative"),
        CheckConstraint("billing_mode IN ('METERED','SUBSCRIPTION_INCLUDED')", name="ck_usage_billing_mode"),
        Index("ix_usage_scope_run", "tenant_id", "workspace_id", "run_id"),
    )

    workflow_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(nullable=False)
    completion_tokens: Mapped[int] = mapped_column(nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    sandbox_compute_seconds: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    managed_charge: Mapped[bool] = mapped_column(default=True, nullable=False, server_default="true")
    billing_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="METERED", server_default="METERED")


class KnowledgeCapsule(ScopedRow, Base):
    __tablename__ = "knowledge_capsules"
    __table_args__ = (
        *scope_constraints("knowledge_capsules"),
        CheckConstraint("propagation_scope IN ('AGENT_PRIVATE','CREW_LOCAL','WORKFLOW_SCOPED','WORKSPACE_QUARANTINE','WORKSPACE_VERIFIED')", name="ck_capsule_scope"),
        CheckConstraint("sensitivity_level IN ('PUBLIC','INTERNAL','CONFIDENTIAL_PII_STRIPPED')", name="ck_capsule_sensitivity"),
        CheckConstraint("status IN ('active','quarantined')", name="ck_capsule_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_capsule_confidence"),
        Index("ix_capsule_source", "tenant_id", "workspace_id", "source_agent_id"),
    )

    capsule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    source_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_role: Mapped[str] = mapped_column(String(200), nullable=False)
    source_domain_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    trigger_preconditions: Mapped[str] = mapped_column(Text, nullable=False)
    distilled_heuristic: Mapped[str] = mapped_column(Text, nullable=False)
    prohibited_contexts: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    propagation_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    source_workflow_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_crew_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    vector_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class LearningPolicy(ScopedRow, Base):
    __tablename__ = "learning_policies"
    __table_args__ = (
        *scope_constraints("learning_policies"),
        UniqueConstraint("tenant_id", "workspace_id", "source_agent_id", "target_agent_id", name="uq_learning_policy_edge"),
        CheckConstraint("propagation_scope IN ('AGENT_PRIVATE','CREW_LOCAL','WORKFLOW_SCOPED','WORKSPACE_QUARANTINE','WORKSPACE_VERIFIED')", name="ck_learning_policy_scope"),
    )

    source_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    propagation_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    allow_heuristics: Mapped[bool] = mapped_column(default=True, nullable=False)
    allow_code_patterns: Mapped[bool] = mapped_column(default=False, nullable=False)
    require_human_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    allowed: Mapped[bool] = mapped_column(default=True, nullable=False)
    source_domain_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    target_domain_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class TransferApplicationLog(ScopedRow, Base):
    __tablename__ = "transfer_application_logs"
    __table_args__ = (
        *scope_constraints("transfer_application_logs"),
        scoped_reference("transfer_application_logs", "knowledge_capsules", "capsule_id"),
        scoped_reference("transfer_application_logs", "workflow_runs", "run_id"),
        CheckConstraint("condition IN ('baseline','treatment')", name="ck_transfer_condition"),
        CheckConstraint("retry_and_error_turns >= 0 AND token_count >= 0 AND latency_ms >= 0", name="ck_transfer_metrics_nonnegative"),
        Index("ix_transfer_pair", "tenant_id", "workspace_id", "capsule_id", "target_agent_id", "condition"),
    )

    capsule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    condition: Mapped[str] = mapped_column(String(12), nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False)
    retry_and_error_turns: Mapped[int] = mapped_column(nullable=False)
    human_approval_rejected: Mapped[bool] = mapped_column(default=False, nullable=False)
    token_count: Mapped[int] = mapped_column(nullable=False)
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    target_domain_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tis_score: Mapped[float | None] = mapped_column(nullable=True)


class TransferCircuitBreaker(ScopedRow, Base):
    __tablename__ = "transfer_circuit_breakers"
    __table_args__ = (
        *scope_constraints("transfer_circuit_breakers"),
        scoped_reference("transfer_circuit_breakers", "knowledge_capsules", "capsule_id"),
        UniqueConstraint("tenant_id", "workspace_id", "capsule_id", "target_agent_id", name="uq_transfer_breaker_pair"),
    )

    capsule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_domain_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tis_score: Mapped[float] = mapped_column(nullable=False)
    application_count: Mapped[int] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class AgentSkill(ScopedRow, Base):
    __tablename__ = "agent_skills"
    __table_args__ = (*scope_constraints("agent_skills"), UniqueConstraint("tenant_id", "workspace_id", "slug", name="uq_agent_skill_scope_slug"))

    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    builtin: Mapped[bool] = mapped_column(default=False, nullable=False)


class WorkspaceBuiltinTool(ScopedRow, Base):
    __tablename__ = "workspace_builtin_tools"
    __table_args__ = (*scope_constraints("workspace_builtin_tools"), UniqueConstraint("tenant_id", "workspace_id", "tool_id", name="uq_workspace_builtin_tool"))

    tool_id: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class WorkflowTopologyVersion(ScopedRow, Base):
    """One generation of a workflow's team topology, with the evidence that produced it and how it performed."""

    __tablename__ = "workflow_topology_versions"
    __table_args__ = (
        *scope_constraints("workflow_topology_versions"),
        UniqueConstraint("tenant_id", "workspace_id", "lineage_id", "version_number", name="uq_topology_lineage_version"),
        CheckConstraint("status IN ('proposed','active','superseded','rolled_back','rejected')", name="ck_topology_status"),
        CheckConstraint("origin IN ('manual','post_run','mid_run','autonomous','baseline')", name="ck_topology_origin"),
        Index("ix_topology_lineage", "tenant_id", "workspace_id", "lineage_id"),
        Index("ix_topology_workflow", "tenant_id", "workspace_id", "workflow_id"),
    )

    lineage_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    parent_version: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    spec: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    mutation_ops_applied: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    evolution_rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diagnoses: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    diff: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    product_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_completeness_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_human_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    avg_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    fitness: Mapped[float | None] = mapped_column(Float, nullable=True)
    runs_observed: Mapped[int] = mapped_column(nullable=False, default=0)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowEvolutionPolicy(ScopedRow, Base):
    """Per-lineage governance: who may promote a new generation and which generation is active."""

    __tablename__ = "workflow_evolution_policies"
    __table_args__ = (
        *scope_constraints("workflow_evolution_policies"),
        UniqueConstraint("tenant_id", "workspace_id", "lineage_id", name="uq_evolution_policy_lineage"),
        CheckConstraint("auto_evolve_policy IN ('SUGGEST_FIRST','FULLY_AUTONOMOUS')", name="ck_evolution_policy"),
    )

    lineage_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    auto_evolve_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="SUGGEST_FIRST")
    active_workflow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    active_version: Mapped[int] = mapped_column(nullable=False)
