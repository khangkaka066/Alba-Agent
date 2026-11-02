"""Configurable subscription limits and tenant-scoped quota checks."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Tenant, TokenUsageLog
from app.models.scope import scoped_session


class Plan(StrEnum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


@dataclass(frozen=True)
class PlanLimits:
    max_monthly_cost_usd: Decimal | None
    max_sandbox_minutes: int | None
    max_workspaces: int | None
    max_persistent_bots: int | None
    max_vector_chunks: int | None


DEFAULT_LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(Decimal("10"), 60, 1, 3, 10_000),
    Plan.PRO: PlanLimits(Decimal("500"), 3_000, 10, 50, 1_000_000),
    Plan.ENTERPRISE: PlanLimits(None, None, None, None, None),
}
_FIELDS = tuple(PlanLimits.__dataclass_fields__)


def plan_limits() -> dict[Plan, PlanLimits]:
    """Load optional JSON overrides while refusing unknown/malformed quota keys."""
    configured = os.environ.get("NEXUS_BILLING_PLAN_LIMITS_JSON", "")
    if not configured:
        return DEFAULT_LIMITS.copy()
    try:
        payload = json.loads(configured)
        if not isinstance(payload, dict):
            raise ValueError
        result = DEFAULT_LIMITS.copy()
        for key, raw in payload.items():
            plan = Plan(key)
            if not isinstance(raw, dict) or set(raw) - set(_FIELDS):
                raise ValueError
            values = {field: getattr(result[plan], field) for field in _FIELDS}
            values.update(raw)
            for field, value in values.items():
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float, str))):
                    raise ValueError(f"Invalid quota value for {plan}.{field}")
            result[plan] = PlanLimits(
                max_monthly_cost_usd=None if values["max_monthly_cost_usd"] is None else Decimal(str(values["max_monthly_cost_usd"])),
                max_sandbox_minutes=None if values["max_sandbox_minutes"] is None else int(values["max_sandbox_minutes"]),
                max_workspaces=None if values["max_workspaces"] is None else int(values["max_workspaces"]),
                max_persistent_bots=None if values["max_persistent_bots"] is None else int(values["max_persistent_bots"]),
                max_vector_chunks=None if values["max_vector_chunks"] is None else int(values["max_vector_chunks"]),
            )
            if any(value is not None and value < 0 for value in (result[plan].max_monthly_cost_usd, result[plan].max_sandbox_minutes, result[plan].max_workspaces, result[plan].max_persistent_bots, result[plan].max_vector_chunks)):
                raise ValueError(f"Quota values for {plan} must be non-negative")
        return result
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise RuntimeError("NEXUS_BILLING_PLAN_LIMITS_JSON is invalid") from error


def limits_for_plan(plan: str) -> PlanLimits:
    try:
        return plan_limits()[Plan(plan)]
    except ValueError as error:
        raise RuntimeError(f"Unknown tenant plan: {plan}") from error


async def tenant_plan(engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID) -> tuple[Plan, PlanLimits]:
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        row = await session.get(Tenant, tenant_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
        try:
            plan = Plan(row.plan)
        except ValueError as error:
            raise RuntimeError("Tenant has an invalid subscription plan") from error
    limits = limits_for_plan(plan.value)
    from app.billing.license import licensed_feature
    if licensed_feature("multi_workspace", tenant_id):
        limits = PlanLimits(limits.max_monthly_cost_usd, limits.max_sandbox_minutes, None, limits.max_persistent_bots, limits.max_vector_chunks)
    return plan, limits


async def enforce_creation_quota(engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID, resource: str) -> None:
    plan, limits = await tenant_plan(engine, tenant_id, workspace_id)
    quota = {"bot": limits.max_persistent_bots, "workspace": limits.max_workspaces}.get(resource)
    if resource not in {"bot", "workspace"}:
        raise ValueError("Unsupported creation quota")
    if quota is None:
        return
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        count = await session.scalar(text("SELECT nexus_tenant_resource_count(:resource, :tenant_id)"), {
            "resource": "persistent_bots" if resource == "bot" else "workspaces",
            "tenant_id": tenant_id,
        })
        if int(count or 0) >= quota:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"{plan.value} plan limit reached for {resource}s")


async def enforce_monthly_sandbox_quota(engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID, additional_seconds: Decimal) -> None:
    plan, limits = await tenant_plan(engine, tenant_id, workspace_id)
    if limits.max_sandbox_minutes is None:
        return
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        consumed = await session.scalar(select(func.coalesce(func.sum(TokenUsageLog.sandbox_compute_seconds), 0)).where(TokenUsageLog.tenant_id == tenant_id, TokenUsageLog.created_at >= start, TokenUsageLog.managed_charge.is_(True)))
    if Decimal(str(consumed or 0)) + additional_seconds > Decimal(limits.max_sandbox_minutes * 60):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"{plan.value} monthly sandbox minutes exhausted")


async def record_sandbox_usage(
    engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID, seconds: Decimal,
    *, run_id: UUID | None = None, agent_name: str = "computer-sandbox",
) -> None:
    if not seconds.is_finite() or seconds < 0:
        raise ValueError("Sandbox compute duration must be finite and non-negative")
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        session.add(TokenUsageLog(
            tenant_id=tenant_id, workspace_id=workspace_id, run_id=run_id,
            agent_name=agent_name, provider="local", model="sandbox",
            prompt_tokens=0, completion_tokens=0, total_cost_usd=Decimal("0"),
            sandbox_compute_seconds=seconds, latency_ms=int(seconds * 1000), managed_charge=True,
        ))
