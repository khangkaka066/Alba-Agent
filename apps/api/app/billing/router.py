"""Authenticated subscription view and signed payment webhook endpoints."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.auth.context import TenantContext, issue_access_token, require_role
from app.billing.license import licensed_feature, verify_license
from app.billing.plans import Plan, enforce_creation_quota, tenant_plan
from app.models import AuditLog, BillingWebhookEvent, Tenant, TenantBudget, User, WorkspaceMember
from app.models.scope import scoped_session
from app.routers.common import get_services

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
ADMIN = Annotated[TenantContext, Depends(require_role("admin", "admin"))]


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


def _secret(name: str) -> bytes:
    value = os.environ.get(name, "")
    if len(value) < 16:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{name} is not configured")
    return value.encode()


def _json_body(raw: bytes) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body is not valid JSON") from error
    if not isinstance(result, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body must be an object")
    return result


def _verify_stripe(raw: bytes, signature: str) -> None:
    try:
        fields = [part.split("=", 1) for part in signature.split(",")]
        timestamp = int(next(value for key, value in fields if key == "t"))
        signatures = [value for key, value in fields if key == "v1"]
    except (ValueError, StopIteration) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed Stripe signature") from error
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expired Stripe signature")
    digest = hmac.new(_secret("NEXUS_STRIPE_WEBHOOK_SECRET"), str(timestamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(digest, item) for item in signatures):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe signature")


def _verify_polar(raw: bytes, headers: dict[str, str]) -> None:
    identifier, timestamp = headers.get("webhook-id", ""), headers.get("webhook-timestamp", "")
    signature = headers.get("webhook-signature", "")
    try:
        sent_at = int(timestamp)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed payment signature") from error
    if not identifier or abs(time.time() - sent_at) > 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expired or incomplete payment signature")
    secret_text = os.environ.get("NEXUS_POLAR_WEBHOOK_SECRET", "")
    if len(secret_text) < 16:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "NEXUS_POLAR_WEBHOOK_SECRET is not configured")
    candidates = [secret_text.encode()]
    if secret_text.startswith("whsec_"):
        try:
            candidates.insert(0, base64.b64decode(secret_text[6:], validate=True))
        except ValueError:
            pass
    message = f"{identifier}.{timestamp}.".encode() + raw
    matched = False
    for key in candidates:
        digest = base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()
        matched |= any(hmac.compare_digest(f"v1,{digest}", item) for item in signature.split())
    if not matched:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payment signature")


def _verify_vietqr(raw: bytes, request: Request) -> None:
    timestamp = request.headers.get("x-nexus-timestamp", "")
    signature = request.headers.get("x-nexus-signature", "")
    try:
        sent_at = int(timestamp)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed VietQR signature") from error
    if abs(time.time() - sent_at) > 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expired VietQR signature")
    digest = hmac.new(_secret("NEXUS_VIETQR_WEBHOOK_SECRET"), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"sha256={digest}", signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid VietQR signature")


async def _apply_event(
    request: Request, provider: str, event_id: str, event_type: str,
    tenant_id: UUID, workspace_id: UUID, plan: Plan | None, credit_usd: Decimal,
    customer_id: str | None, subscription_id: str | None, period_end: datetime | None,
) -> bool:
    if credit_usd < 0 or not credit_usd.is_finite():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Credit top-up must be a finite non-negative USD amount")
    engine = get_services(request).engine
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        inserted = await session.scalar(
            insert(BillingWebhookEvent)
            .values(tenant_id=tenant_id, workspace_id=workspace_id, provider=provider, event_id=event_id, event_type=event_type)
            .on_conflict_do_nothing(constraint="uq_billing_event_provider_id")
            .returning(BillingWebhookEvent.id)
        )
        if inserted is None:
            return False
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment tenant was not found")
        if plan is not None:
            tenant.plan = plan.value
            tenant.billing_provider = provider
            tenant.billing_customer_id = customer_id
            tenant.billing_subscription_id = subscription_id
            tenant.billing_period_end = period_end
        if credit_usd:
            await session.execute(
                update(TenantBudget).where(TenantBudget.tenant_id == tenant_id)
                .values(remaining_usd=TenantBudget.remaining_usd + credit_usd)
            )
    return True


def _payment_fields(event: dict[str, Any], provider: str) -> tuple[str, str, UUID, UUID, Plan | None, Decimal, str | None, str | None, datetime | None]:
    data = event.get("data", {})
    obj = data.get("object", data) if isinstance(data, dict) else {}
    metadata = obj.get("metadata", {}) if isinstance(obj, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    tenant_raw = metadata.get("tenant_id") or obj.get("tenant_id")
    workspace_raw = metadata.get("workspace_id") or obj.get("workspace_id")
    event_id, event_type = event.get("id"), event.get("type")
    if not isinstance(event_id, str) or not isinstance(event_type, str) or not isinstance(tenant_raw, str) or not isinstance(workspace_raw, str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment event is missing event or tenant metadata")
    try:
        tenant_id, workspace_id = UUID(tenant_raw), UUID(workspace_raw)
        raw_plan = metadata.get("nexus_plan") or metadata.get("plan")
        product_id = obj.get("product_id")
        items = obj.get("items")
        if not product_id and isinstance(items, dict):
            item_rows = items.get("data", [])
            if item_rows and isinstance(item_rows[0], dict):
                price = item_rows[0].get("price", {})
                product_id = price.get("id") if isinstance(price, dict) else None
        if not raw_plan and isinstance(product_id, str):
            plan_map = json.loads(os.environ.get("NEXUS_BILLING_PRODUCT_PLANS_JSON", "{}"))
            provider_map = plan_map.get(provider, {}) if isinstance(plan_map, dict) else {}
            raw_plan = provider_map.get(product_id) if isinstance(provider_map, dict) else None
        plan = Plan(raw_plan) if raw_plan else None
        event_type = event_type.lower()
        object_status = str(obj.get("status", "")).lower()
        if event_type in {"checkout.session.completed", "checkout.updated"} and object_status not in {"succeeded", "paid", "active"} and obj.get("payment_status") != "paid":
            plan = None
        if "subscription" in event_type and event_type not in {"subscription.active"} and object_status not in {"active", "trialing"}:
            plan = Plan.FREE if event_type in {"subscription.past_due", "subscription.revoked", "subscription.canceled", "customer.subscription.deleted"} else None
        if event_type in {"customer.subscription.deleted", "subscription.canceled", "subscription.revoked", "subscription.past_due", "invoice.payment_failed"}:
            plan = Plan.FREE
        paid_event = event_type in {
            "invoice.payment_succeeded", "checkout.session.completed", "payment_intent.succeeded",
            "order.paid", "payment.succeeded", "vietqr.payment.paid",
        }
        if provider == "stripe" and event_type == "checkout.session.completed":
            paid_event = obj.get("payment_status") == "paid"
        raw_credit = metadata.get("nexus_credit_usd", "") if paid_event else "0"
        if paid_event and not raw_credit and isinstance(product_id, str):
            credit_map = json.loads(os.environ.get("NEXUS_BILLING_PRODUCT_CREDITS_JSON", "{}"))
            provider_map = credit_map.get(provider, {}) if isinstance(credit_map, dict) else {}
            raw_credit = provider_map.get(product_id, "0") if isinstance(provider_map, dict) else "0"
        credit = Decimal(str(raw_credit))
        period_end_raw = obj.get("current_period_end") or obj.get("period_end")
        if isinstance(period_end_raw, (int, float)) or (isinstance(period_end_raw, str) and period_end_raw.isdigit()):
            period_end = datetime.fromtimestamp(int(period_end_raw), timezone.utc)
        elif isinstance(period_end_raw, str):
            period_end = datetime.fromisoformat(period_end_raw.replace("Z", "+00:00"))
            if period_end.tzinfo is None:
                period_end = period_end.replace(tzinfo=timezone.utc)
        else:
            period_end = None
    except (ValueError, TypeError, InvalidOperation, OSError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment event metadata is invalid") from error
    customer = obj.get("customer") or obj.get("customer_id")
    subscription = obj.get("subscription") or obj.get("id")
    return event_id, event_type, tenant_id, workspace_id, plan, credit, str(customer) if customer else None, str(subscription) if subscription else None, period_end


async def _dispatch(provider: str, event: dict[str, Any], request: Request) -> dict[str, bool]:
    try:
        fields = _payment_fields(event, provider)
    except (AttributeError, TypeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment event structure is invalid") from error
    event_id, event_type, tenant_id, workspace_id, plan, credit, customer, subscription, period_end = fields
    changed = await _apply_event(request, provider, event_id, event_type, tenant_id, workspace_id, plan, credit, customer, subscription, period_end)
    return {"accepted": True, "applied": changed}


@router.get("/plan")
async def get_plan(request: Request, context: READ) -> dict[str, object]:
    plan, limits = await tenant_plan(get_services(request).engine, context.tenant_id, context.workspace_id)
    return {"plan": plan.value, "limits": {key: str(value) if isinstance(value, Decimal) else value for key, value in limits.__dict__.items()}}


@router.get("/audit-logs")
async def list_audit_logs(request: Request, context: ADMIN) -> list[dict[str, object]]:
    plan, _ = await tenant_plan(get_services(request).engine, context.tenant_id, context.workspace_id)
    if plan != Plan.ENTERPRISE and not licensed_feature("audit_logs", context.tenant_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Audit log access requires an Enterprise plan or license")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200))).all()
        return [{
            "id": str(row.id), "actor_id": str(row.actor_id) if row.actor_id else None,
            "action": row.action, "target_type": row.target_type,
            "target_id": str(row.target_id) if row.target_id else None,
            "details": row.details, "created_at": row.created_at.isoformat(),
        } for row in rows]


@router.get("/license")
async def get_license(context: READ) -> dict[str, object]:
    try:
        license_data = verify_license()
    except ValueError:
        return {"valid": False, "features": []}
    if license_data.tenant_id is not None and license_data.tenant_id != context.tenant_id:
        return {"valid": False, "features": []}
    return {"valid": True, "expires_at": license_data.expires_at, "features": sorted(license_data.features)}


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, request: Request, context: ADMIN) -> dict[str, str]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Workspace name is invalid")
    services = get_services(request)
    await enforce_creation_quota(services.engine, context.tenant_id, context.workspace_id, "workspace")
    workspace_id, user_id = uuid4(), uuid4()
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        source = await session.get(User, context.user_id)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User is unavailable")
        await session.execute(
            text("SELECT nexus_create_workspace(:tenant_id, :workspace_id, :new_id, :name)"),
            {"tenant_id": context.tenant_id, "workspace_id": context.workspace_id, "new_id": workspace_id, "name": name},
        )
        await session.execute(text("SELECT set_config('nexus.workspace_id', :workspace_id, true)"), {"workspace_id": str(workspace_id)})
        session.add(User(
            id=user_id, tenant_id=context.tenant_id, workspace_id=workspace_id,
            email=source.email, password_hash=source.password_hash, display_name=source.display_name,
        ))
        session.add(WorkspaceMember(tenant_id=context.tenant_id, workspace_id=workspace_id, user_id=user_id, role="owner"))
    token = issue_access_token(TenantContext(context.tenant_id, workspace_id, user_id, "owner"))
    return {"workspace_id": str(workspace_id), "user_id": str(user_id), "access_token": token}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    _verify_stripe(raw, request.headers.get("stripe-signature", ""))
    return await _dispatch("stripe", _json_body(raw), request)


@router.post("/webhooks/polar")
async def polar_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    _verify_polar(raw, dict(request.headers))
    event = _json_body(raw)
    if "id" not in event and request.headers.get("webhook-id"):
        event["id"] = request.headers["webhook-id"]
    return await _dispatch("polar", event, request)


@router.post("/webhooks/vietqr")
async def vietqr_webhook(request: Request) -> dict[str, bool]:
    raw = await request.body()
    _verify_vietqr(raw, request)
    event = _json_body(raw)
    return await _dispatch("vietqr", event, request)
