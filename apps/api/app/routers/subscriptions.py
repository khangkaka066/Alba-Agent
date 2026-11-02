"""Subscription plan connectors: detect mounted CLI logins, import them, GitHub Copilot device login, live verification."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, update

from app.auth.context import TenantContext
from app.models import ModelCredential
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from app.routers.providers import BUILD, READ, CredentialView, RUNTIME_PROVIDER, _resolve_public_url, _view
from nexus_model_gateway import GatewayRequest
from nexus_model_gateway.provider_presets import PRESETS_BY_ID
from nexus_model_gateway.router import Provider
from nexus_model_gateway.subscription_connectors import (
    COPILOT_DEFAULT_API, CONNECTORS, CONNECTORS_BY_ID, MOUNTED_FILES, PARSERS, SUBSCRIPTION_PRESETS,
    ConnectorError, ConnectorSpec, ImportedSubscription, billing_for, list_copilot_models, poll_device_login, start_device_login,
)

router = APIRouter(prefix="/api/v1/settings/subscriptions", tags=["subscription-connectors"])

MAX_CREDENTIAL_FILE_BYTES = 256 * 1024
DEVICE_FLOW_KEY = "nexus:subscription:copilot-device:{tenant}:{workspace}:{flow}"
LOCAL_BRIDGE_PREFIX = "http://host.docker.internal:"


def _mount_root() -> Path:
    return Path(os.environ.get("NEXUS_SUBSCRIPTIONS_DIR", "/var/lib/nexus/subscriptions"))


def _mounted_enabled() -> bool:
    # The mount holds the operator's own logins, so it is opt-in and meant for single-tenant local stacks.
    return os.environ.get("NEXUS_MOUNTED_SUBSCRIPTIONS_ENABLED", "false").lower() == "true"


def _read_mounted(connector_id: str) -> tuple[str, str] | None:
    root = _mount_root()
    for relative in MOUNTED_FILES.get(connector_id, ()):
        path = root / relative
        try:
            if path.is_file() and path.stat().st_size <= MAX_CREDENTIAL_FILE_BYTES:
                return relative, path.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _describe(connector_id: str) -> dict[str, object]:
    """What is mounted for a connector, without ever returning a secret."""
    if not _mounted_enabled():
        return {"enabled": False, "found": False}
    mounted = _read_mounted(connector_id)
    if mounted is None:
        return {"enabled": True, "found": False}
    relative, text = mounted
    try:
        parsed = PARSERS[connector_id](text)
    except ConnectorError as error:
        return {"enabled": True, "found": True, "valid": False, "file": relative, "error": str(error)}
    return {
        "enabled": True, "found": True, "valid": True, "file": relative, "plan": parsed.settings.get("plan"),
        "auth_kind": parsed.settings.get("auth_kind"), "expires_at": parsed.expires_at.isoformat() if parsed.expires_at else None,
    }


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: str = Field(min_length=3, max_length=60)
    source: Literal["mounted", "paste"]
    content: SecretStr | None = Field(default=None, min_length=1, max_length=MAX_CREDENTIAL_FILE_BYTES)
    base_url: str | None = Field(default=None, max_length=1000)
    is_default: bool = True


class DevicePollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_id: str = Field(min_length=8, max_length=64)
    is_default: bool = True


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, min_length=1, max_length=200)


async def _check_bridge_url(base_url: str) -> str:
    cleaned = base_url.rstrip("/")
    if cleaned.startswith(LOCAL_BRIDGE_PREFIX):
        return cleaned
    await _resolve_public_url(cleaned)
    return cleaned


async def _store_subscription(
    request: Request, context: TenantContext, connector: ConnectorSpec, imported: ImportedSubscription,
    base_url: str | None, is_default: bool, models: list[str] | None = None,
) -> CredentialView:
    services = get_services(request)
    cipher = services._store()._cipher
    provider = RUNTIME_PROVIDER[connector.id]
    auth_kind = imported.settings.get("auth_kind", "api_key")
    settings: dict[str, object] = {**imported.settings, "billing_mode": billing_for(connector.id, auth_kind, base_url is not None)}
    if imported.expires_at is not None:
        settings["expires_at"] = imported.expires_at.isoformat()
    serialized = next(iter(imported.secrets.values())) if set(imported.secrets) == {"api_key"} else cipher.encode_fields(imported.secrets)
    resolved_base = base_url or PRESETS_BY_ID[connector.id].base_url
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(
            ModelCredential.tenant_id == context.tenant_id, ModelCredential.workspace_id == context.workspace_id,
            ModelCredential.provider == provider, ModelCredential.name == connector.id,
        ))
        if row is None:
            row = ModelCredential(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                  provider=provider, name=connector.id, encrypted_key="", key_version=1)
            session.add(row)
        row.encrypted_key = cipher.encrypt(serialized, context.tenant_id, context.workspace_id, provider)
        row.preset_id = connector.id
        row.base_url = resolved_base
        row.status = "untested"
        row.is_default = is_default
        row.available_models = models or list(connector.models)
        row.settings = settings
        row.safe_error = None
        if is_default:
            await session.execute(update(ModelCredential).where(
                ModelCredential.tenant_id == context.tenant_id, ModelCredential.workspace_id == context.workspace_id,
                ModelCredential.provider == provider, ModelCredential.id != row.id,
            ).values(is_default=False))
        await session.flush()
        await session.refresh(row)
        return _view(row, cipher)


@router.get("/connectors")
async def list_connectors(_: READ) -> dict[str, object]:
    return {"connectors": [{**item.as_dict(), "mounted": _describe(item.id)} for item in CONNECTORS]}


@router.post("/import", response_model=CredentialView, status_code=status.HTTP_201_CREATED)
async def import_subscription(body: ImportRequest, request: Request, context: BUILD) -> CredentialView:
    connector = CONNECTORS_BY_ID.get(body.connector_id)
    if connector is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown subscription connector")
    if body.source == "mounted":
        if not _mounted_enabled():
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Mounted subscription logins are disabled on this server")
        mounted = _read_mounted(connector.id)
        if mounted is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No login for this plan is mounted; see data/subscriptions/README.md")
        text = mounted[1]
    else:
        if body.content is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Paste the credential file or token")
        text = body.content.get_secret_value()
    try:
        imported = PARSERS[connector.id](text)
    except ConnectorError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    base_url = await _check_bridge_url(body.base_url) if body.base_url else None
    if connector.needs_base_url and imported.settings.get("auth_kind") == "oauth_token" and base_url is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, connector.notice)
    if connector.id == "github_copilot" and "oauth_token" not in imported.secrets:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use the device code sign-in for GitHub Copilot")
    return await _store_subscription(request, context, connector, imported, base_url, body.is_default)


@router.post("/github-copilot/device/start")
async def copilot_device_start(request: Request, context: BUILD) -> dict[str, object]:
    try:
        device = await start_device_login()
    except (httpx.HTTPError, ConnectorError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub could not start the device login") from error
    flow_id = uuid4().hex
    redis = get_services(request).redis
    key = DEVICE_FLOW_KEY.format(tenant=context.tenant_id, workspace=context.workspace_id, flow=flow_id)
    await redis.set(key, device.device_code, ex=device.expires_in)
    return {"flow_id": flow_id, "user_code": device.user_code, "verification_uri": device.verification_uri,
            "expires_in": device.expires_in, "interval": device.interval}


@router.post("/github-copilot/device/poll")
async def copilot_device_poll(body: DevicePollRequest, request: Request, context: BUILD) -> dict[str, object]:
    services = get_services(request)
    key = DEVICE_FLOW_KEY.format(tenant=context.tenant_id, workspace=context.workspace_id, flow=body.flow_id)
    device_code = await services.redis.get(key)
    if device_code is None:
        return {"status": "expired"}
    try:
        result = await poll_device_login(str(device_code))
    except (httpx.HTTPError, ConnectorError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub could not check the device login") from error
    if result.status != "authorized" or result.oauth_token is None:
        if result.status in ("expired", "denied"):
            await services.redis.delete(key)
        return {"status": result.status, "interval": result.interval}
    await services.redis.delete(key)
    connector = CONNECTORS_BY_ID["github_copilot"]
    models: list[str] | None = None
    try:
        from app.models.gateway_store import COPILOT_BROKER
        models = await list_copilot_models(COPILOT_BROKER, result.oauth_token) or None
    except (httpx.HTTPError, ConnectorError):
        models = None
    imported = ImportedSubscription({"oauth_token": result.oauth_token}, {"auth_kind": "device_flow", "plan": "copilot"})
    credential = await _store_subscription(request, context, connector, imported, COPILOT_DEFAULT_API, body.is_default, models)
    return {"status": "authorized", "credential": credential.model_dump(mode="json")}


def _safe_failure(error: BaseException) -> str:
    code = getattr(error, "status_code", None)
    if isinstance(error, ConnectorError):
        return str(error)
    if code in (401, 403):
        return "The plan rejected the credential. It may have expired; sign in again and re-import it."
    if code == 404:
        return "The plan does not offer this model, or the bridge URL is wrong."
    if code == 429:
        return "The plan's usage limit was reached. Try again later or pick another model."
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "The plan endpoint did not answer in time."
    return "The test call failed. Check the bridge URL, the model name and that the plan is active."


@router.post("/credentials/{credential_id}/verify")
async def verify_subscription(credential_id: UUID, body: VerifyRequest, request: Request, context: BUILD) -> dict[str, object]:
    """Make one real one-token call through the same resolution path that workflow runs use."""
    services = get_services(request)
    cipher = services._store()._cipher
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id))
        if row is None:
            raise not_found("Provider credential was not found in this workspace")
        provider, preset_id, models = row.provider, row.preset_id, list(row.available_models)
    if preset_id not in SUBSCRIPTION_PRESETS and preset_id not in PRESETS_BY_ID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown credential type")
    model = (body.model or (models[0] if models else "")).split("/", 1)[-1]
    if not model:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a model to test")
    started = datetime.now(timezone.utc)
    reply, cost = "", "0"
    billing_mode = "SUBSCRIPTION_INCLUDED"
    ok, error_text = True, None
    try:
        result = await services.gateway().complete(GatewayRequest(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id, provider=cast(Provider, provider), model=model,
            messages=({"role": "user", "content": "Reply with the single word OK."},),
            max_input_tokens=256, max_output_tokens=16, billing_mode="byok", agent_name="subscription-verify",
            credential_id=credential_id,
        ))
        reply, billing_mode, cost = result.content.strip()[:80], result.usage.billing_mode, format(result.usage.total_cost_usd.normalize(), 'f')
    except Exception as error:  # noqa: BLE001 - provider failures are reported as a safe message, never a traceback
        ok, error_text = False, _safe_failure(error)
    latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id))
        if row is None:
            raise not_found("Provider credential was not found in this workspace")
        row.status = "connected" if ok else "error"
        row.last_tested_at = datetime.now(timezone.utc)
        row.safe_error = error_text
        view = _view(row, cipher)
    return {"ok": ok, "status": view.status, "model": model, "latency_ms": latency_ms, "billing_mode": billing_mode,
            "cost_usd": cost, "reply": reply, "error": error_text,
            "credential": view.model_dump(mode="json")}

