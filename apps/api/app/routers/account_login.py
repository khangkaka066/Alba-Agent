"""Local account sign-in and a scoped OpenAI-compatible adapter to official applications."""
from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import account_cli
from app.google_account import GoogleAccounts, GoogleLogins
from app.account_models import AccountModels
from app.auth.context import TenantContext
from app.auth.local import local_mode_enabled
from app.models import AuditLog, ModelCredential
from app.models.scope import scoped_session
from app.routers.common import get_services
from app.routers.providers import BUILD, READ, CredentialView, _view
from nexus_model_gateway import CredentialCipher
from nexus_model_gateway.router import SUBSCRIPTION_INCLUDED

router = APIRouter(tags=["account-login"])
PREFIX = "/api/v1/settings/subscriptions/accounts"


def local_only() -> None:
    if not local_mode_enabled():
        raise HTTPException(403, "Account applications are available only on the local desktop")


def provider_spec(provider: str) -> dict[str, str]:
    if provider not in account_cli.PROVIDERS:
        raise HTTPException(404, "Account provider not found")
    return account_cli.PROVIDERS[provider]


@router.get(PREFIX)
async def catalog(context: READ) -> dict[str, object]:
    return {"local": local_mode_enabled(), "providers": [{"id": key, **value, "installed": bool(account_cli.executable(key)) if local_mode_enabled() else False} for key, value in account_cli.PROVIDERS.items()]}


@router.post(PREFIX + "/{provider}/prepare")
async def prepare_login(provider: str, context: BUILD) -> dict[str, object]:
    local_only()
    provider_spec(provider)
    profile = account_cli.profile_for(context.tenant_id, context.workspace_id, provider)
    account_cli.prepare(profile, provider)
    if not account_cli.executable(provider):
        raise HTTPException(409, "Install the official application using the installation link, then return to sign in")
    return {"provider": provider, "tenant_id": str(context.tenant_id), "workspace_id": str(context.workspace_id)}


def login_registry(request: Request) -> GoogleLogins:
    registry = getattr(request.app.state, "google_logins", None)
    if registry is None:
        registry = GoogleLogins()
        request.app.state.google_logins = registry
    return registry


def google_accounts(request: Request) -> GoogleAccounts:
    pool = getattr(request.app.state, "google_accounts", None)
    if pool is None:
        pool = GoogleAccounts()
        request.app.state.google_accounts = pool
    return pool


async def account_models(request: Request, profile: Path, provider: str) -> tuple[list[dict[str, str]], str]:
    if provider == "gemini":
        return await google_accounts(request).catalog(profile)
    if provider == "codex":
        cache = getattr(request.app.state, "account_models", None)
        if cache is None:
            cache = AccountModels()
            request.app.state.account_models = cache
        return await cache.codex(profile)
    return [], ""


@router.post(PREFIX + "/{provider}/login")
async def google_login(provider: str, request: Request, context: BUILD) -> dict[str, object]:
    local_only()
    provider_spec(provider)
    if account_cli.executable(provider) is None:
        raise HTTPException(409, "Install the official account application first")
    if provider == "gemini":
        await google_accounts(request).discard(account_cli.profile_for(context.tenant_id, context.workspace_id, provider))
    flow = await login_registry(request).start(str(context.tenant_id), str(context.workspace_id), str(context.user_id), account_cli.profile_for(context.tenant_id, context.workspace_id, provider), provider)
    return {"flow_id": flow, "status": "pending"}


@router.get(PREFIX + "/{provider}/login/{flow}")
async def google_login_state(provider: str, flow: UUID, request: Request, context: READ) -> dict[str, str]:
    local_only()
    provider_spec(provider)
    state = login_registry(request).state(flow.hex, str(context.tenant_id), str(context.workspace_id), str(context.user_id), provider)
    if state is None:
        raise HTTPException(404, "Sign-in session not found")
    return {"status": state}


@router.post(PREFIX + "/{provider}/login/{flow}/cancel", status_code=204)
async def cancel_login(provider: str, flow: UUID, request: Request, context: BUILD) -> Response:
    local_only()
    provider_spec(provider)
    if not await login_registry(request).cancel(flow.hex, str(context.tenant_id), str(context.workspace_id), str(context.user_id), provider):
        raise HTTPException(404, "Sign-in session not found")
    return Response(status_code=204)


@router.post(PREFIX + "/{provider}/connect", response_model=CredentialView)
async def connect(provider: str, request: Request, context: BUILD) -> CredentialView:
    local_only()
    spec = provider_spec(provider)
    profile = account_cli.profile_for(context.tenant_id, context.workspace_id, provider)
    # Authentication is owned by the official application. Never accept or read vendor tokens.
    limited = False
    try:
        answer = await google_accounts(request).answer(profile, "Reply with exactly NEXUS_ACCOUNT_OK, with no other text.") if provider == "gemini" else await account_cli.run(profile, provider, "Reply with exactly NEXUS_ACCOUNT_OK, with no other text.")
    except account_cli.AccountCliRateLimited as error:
        if not await account_cli.authenticated(profile, provider):
            raise HTTPException(409, "Complete sign-in with the official application first") from error
        limited = True
        answer = {"content": ""}
    except (account_cli.AccountCliError, TimeoutError) as error:
        raise HTTPException(409, "Sign-in could not be verified. Finish signing in with the official application, then check again") from error
    if not limited and "NEXUS_ACCOUNT_OK" not in answer["content"]:
        raise HTTPException(502, "The provider did not complete the connection check")
    services = get_services(request)
    cipher = services._store()._cipher
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.preset_id == spec["preset"], ModelCredential.name == f"account:{provider}"))
        if row is None:
            row = ModelCredential(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id, provider=spec["provider"], name=f"account:{provider}", preset_id=spec["preset"], encrypted_key="", key_version=1)
            session.add(row)
        # This is a revocable loopback capability, NOT a provider API key or session token.
        capability = f"nx-cli-{context.tenant_id.hex}.{context.workspace_id.hex}.{row.id.hex}.{secrets.token_urlsafe(32)}"
        row.encrypted_key = cipher.encrypt(capability, context.tenant_id, context.workspace_id, row.provider)
        row.settings = {"auth_kind": "official_cli", "account_provider": provider, "billing_mode": SUBSCRIPTION_INCLUDED}
        row.status = "limited" if limited else "connected"
        row.safe_error = "The account is signed in, but the provider returned 429. Retry after its usage limit resets" if limited else None
        row.base_url = None
        models, current = await account_models(request, profile, provider)
        row.available_models = [account_cli.alias(provider, item["id"]) for item in models] or [account_cli.alias(provider)]
        row.default_models = {"orchestrator": account_cli.alias(provider, current or "default")}
        row.is_default = False  # Connecting an account never displaces a working API provider.
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id, action="account.connected", target_type="model_credential", target_id=row.id, details={"provider": provider}))
        await session.flush()
        await session.refresh(row)
        return _view(row, cipher)


@router.delete(PREFIX + "/{provider}", status_code=204)
async def disconnect(provider: str, request: Request, context: BUILD) -> Response:
    local_only()
    spec = provider_spec(provider)
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(ModelCredential).where(ModelCredential.preset_id == spec["preset"], ModelCredential.name == f"account:{provider}"))).all()
        for row in rows:
            row.status = "disconnected"
            row.is_default = False
            row.encrypted_key = services._store()._cipher.encrypt(secrets.token_urlsafe(32), context.tenant_id, context.workspace_id, row.provider)
            session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id, action="account.disconnected", target_type="model_credential", target_id=row.id, details={"provider": provider}))

    if provider == "gemini":
        await google_accounts(request).discard(account_cli.profile_for(context.tenant_id, context.workspace_id, provider))
    return Response(status_code=204)


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str = Field(min_length=1, max_length=180)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=256)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    tool_choice: Any = None
    response_format: dict[str, Any] | None = None
    stream: bool = False
    max_tokens: int = Field(default=4096, ge=1, le=131072)


def completion_prompt(body: CompletionRequest) -> str:
    value = {"messages": body.messages, "max_output_tokens": body.max_tokens}
    prompt = "You are the text inference component of Alba Agent. All workspace actions are handled separately by Alba Agent. Do not read files, run commands, browse or invoke native application tools. Answer only from the supplied conversation.\n"
    if body.response_format:
        prompt += "Return only JSON matching this response format: " + json.dumps(body.response_format) + "\n"
    if body.tools:
        prompt += 'Return exactly one JSON object with keys "content" (string or null) and "tool_calls" (array of {"id":string,"name":string,"arguments":object}). Only request functions from this list; do not execute them yourself. Use an empty array when no function is required.\n'
        prompt += json.dumps({"tools": body.tools, "tool_choice": body.tool_choice}) + "\n"
    result = prompt + json.dumps(value, ensure_ascii=False)
    if len(result) > 500_000:
        raise HTTPException(413, "The conversation is too large for this account connection")
    return result


def response_message(content: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    if not tools:
        return {"role": "assistant", "content": content}
    value = content.strip()
    if value.startswith("```json") and value.endswith("```"):
        value = value[7:-3].strip()
    try:
        parsed = json.loads(value)
        allowed = {tool["function"]["name"] for tool in tools}
        calls = parsed.get("tool_calls", [])
        if not isinstance(calls, list) or len(calls) > 32:
            raise ValueError("Invalid tool calls")
        converted = []
        for call in calls:
            if call["name"] not in allowed or not isinstance(call["arguments"], dict):
                raise ValueError("Unknown function")
            converted.append({"id": str(call.get("id") or "call_" + uuid4().hex), "type": "function", "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}})
        result: dict[str, Any] = {"role": "assistant", "content": parsed.get("content")}
        if result["content"] is not None and not isinstance(result["content"], str):
            raise ValueError("Invalid content")
        if converted:
            result["tool_calls"] = converted
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(502, "The account model returned an invalid function response. Retry the request") from error


async def runtime_identity(request: Request) -> tuple[UUID, UUID, str]:
    local_only()
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer nx-cli-"):
        raise HTTPException(401, "Account connection required")
    capability = value[7:]
    try:
        tenant, workspace, credential, _secret = capability.removeprefix("nx-cli-").split(".")
        tenant_id, workspace_id, credential_id = UUID(tenant), UUID(workspace), UUID(credential)
    except ValueError as error:
        raise HTTPException(401, "Invalid account connection") from error
    services = get_services(request)
    async with scoped_session(services.engine, tenant_id, workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id, ModelCredential.status.in_(("connected", "limited"))))
        if row is None or row.settings.get("auth_kind") != "official_cli":
            raise HTTPException(401, "Account connection is no longer active")
        stored = CredentialCipher.decode_fields(services._store()._cipher.decrypt(row.encrypted_key, tenant_id, workspace_id, row.provider)).get("api_key", "")
        if not hmac.compare_digest(stored, capability):
            raise HTTPException(401, "Invalid account connection")
        provider = str(row.settings["account_provider"])
        return tenant_id, workspace_id, provider


@router.post("/api/v1/account-runtime/chat/completions")
async def complete(body: CompletionRequest, request: Request) -> Any:
    tenant, workspace, provider = await runtime_identity(request)
    # Aliases bind the selected model to this exact account, never a fallback API credential.
    try:
        model = account_cli.alias_model(body.model, provider)
        if provider == "codex" and model != "default":
            catalog, _ = await account_models(request, account_cli.profile_for(tenant, workspace, provider), provider)
            if model not in {item["id"] for item in catalog}:
                raise HTTPException(400, "This model or effort is no longer available on the selected account")
        elif provider not in {"gemini", "codex"} and model != "default":
            raise HTTPException(400, "This model is not available on the selected account")
        profile = account_cli.profile_for(tenant, workspace, provider)
        result = await google_accounts(request).answer(profile, completion_prompt(body), model) if provider == "gemini" else await account_cli.run(profile, provider, completion_prompt(body), model)
    except account_cli.AccountCliError as error:
        raise HTTPException(502, str(error)) from error
    message = response_message(result["content"], body.tools)
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    response = {"id": "chatcmpl-" + uuid4().hex, "object": "chat.completion", "created": int(time.time()), "model": body.model, "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {**result["usage"], "total_tokens": sum(result["usage"].values())}}
    if not body.stream:
        return response
    async def chunks() -> AsyncIterator[str]:
        delta = {**message}
        for index, call in enumerate(delta.get("tool_calls", [])):
            call["index"] = index
        yield "data: " + json.dumps({**response, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) + "\n\n"
        yield "data: " + json.dumps({**response, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(chunks(), media_type="text/event-stream")
