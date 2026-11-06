"""Workspace-scoped provider catalog, encrypted credentials, and connectivity checks."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select, update

from app.auth.context import TenantContext, require_role
from app.models import ModelCredential, TenantBudget
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from nexus_model_gateway.provider_presets import PRESETS, PRESETS_BY_ID

router = APIRouter(prefix="/api/v1/settings", tags=["provider-settings"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]

RUNTIME_PROVIDER: dict[str, str] = {
    "shopaikey": "openai", "openrouter": "openrouter", "custom_openai_gateway": "openai",
    "openai_subscription": "openai", "claude_subscription": "anthropic", "gemini_subscription": "gemini",
    "github_copilot": "openai", "cliproxyapi": "openai",
    "openai": "openai", "anthropic": "anthropic", "google_gemini": "gemini",
    "deepseek": "deepseek", "groq": "groq", "mistral": "mistral", "together_ai": "together_ai",
    "ollama": "ollama", "lm_studio": "vllm", "local_vllm": "vllm",
}


class CredentialWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str = Field(min_length=2, max_length=80)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    secrets: dict[str, SecretStr] = Field(default_factory=dict, max_length=8)
    base_url: str | None = Field(default=None, max_length=1000)
    is_default: bool = False
    default_models: dict[str, str] = Field(default_factory=dict, max_length=16)
    settings: dict[str, str] = Field(default_factory=dict, max_length=32)

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(key) > 80 or len(item) > 500 for key, item in value.items()):
            raise ValueError("Provider settings are too large")
        return value

    @field_validator("secrets")
    @classmethod
    def validate_secrets(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        if any(len(key) > 80 or len(secret.get_secret_value()) > 4096 for key, secret in value.items()):
            raise ValueError("Provider credential fields are too large")
        return value


class CredentialView(BaseModel):
    id: UUID
    preset_id: str
    provider: str
    name: str
    masked_key: str | None
    status: str
    base_url: str | None
    is_default: bool
    available_models: list[str]
    default_models: dict[str, str]
    settings: dict[str, Any]
    balance: dict[str, object] | None
    last_tested_at: datetime | None
    safe_error: str | None


class LocalDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = Field(min_length=12, max_length=1000)


def _runtime_provider(preset_id: str) -> str:
    if preset_id not in PRESETS_BY_ID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown provider preset")
    return RUNTIME_PROVIDER.get(preset_id, preset_id)


def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "••••••••"
    return f"{secret[:3]}-****...{secret[-4:]}"


def _view(row: ModelCredential, cipher: Any) -> CredentialView:
    # Secret is decrypted only to make a short, non-reversible display mask.
    preset_id = row.preset_id or row.name
    decrypted = cipher.decrypt(row.encrypted_key, row.tenant_id, row.workspace_id, row.provider)
    secret_fields = cipher.decode_fields(decrypted)
    masked_secret = secret_fields.get("api_key") or next(iter(secret_fields.values()), "")
    return CredentialView(
        id=row.id, preset_id=row.preset_id or row.name, provider=row.provider, name=row.name,
        masked_key=None if PRESETS_BY_ID.get(preset_id) and PRESETS_BY_ID[preset_id].local else (_mask(masked_secret) if masked_secret else None), status=row.status.upper(), base_url=row.base_url,
        is_default=row.is_default, available_models=row.available_models,
        default_models=row.default_models, settings=row.settings,
        balance=row.live_balance,
        last_tested_at=row.last_tested_at, safe_error=row.safe_error,
    )


async def _resolve_public_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Custom provider URLs must be HTTPS without credentials or query parameters")
    try:
        addresses = await __import__("asyncio").to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provider hostname could not be resolved") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Custom provider URL resolves to a non-public address")


def _base_url(preset_id: str, override: str | None) -> str | None:
    preset = PRESETS_BY_ID[preset_id]
    if not override:
        return preset.base_url
    if preset.local:
        if not override.startswith("http://host.docker.internal:"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Local endpoints must use the approved host bridge")
        return override.rstrip("/")
    return override.rstrip("/")


@router.get("/provider-presets")
async def provider_presets() -> dict[str, object]:
    categories: dict[str, list[dict[str, object]]] = {key: [] for key in ("subscription", "unified", "direct", "local", "media", "tools", "channel")}
    for preset in PRESETS:
        categories[preset.category].append(preset.as_dict())
    return {"categories": categories}


@router.post("/providers/ollama/discover")
async def discover_local_models(body: LocalDiscoveryRequest, _: BUILD) -> dict[str, object]:
    base_url = _base_url("ollama", body.base_url)
    assert base_url is not None
    try:
        models, _balance = await _ping("ollama", base_url, "", None)
    except (httpx.HTTPError, ValueError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not discover models from the local Ollama endpoint") from error
    return {"base_url": base_url, "available_models": models}


NON_CHAT_PARTS = ("embed", "whisper", "tts", "dall-e", "image", "moderation", "veo", "speech", "rerank")


def _is_chat_model(name: str) -> bool:
    return not any(part in name.lower() for part in NON_CHAT_PARTS)


PLATFORM_MODELS: tuple[tuple[str, str], ...] = (
    ("NEXUS_OPENAI_API_KEY", "gpt-4.1-mini"), ("NEXUS_ANTHROPIC_API_KEY", "claude-sonnet-4-6"),
    ("NEXUS_GEMINI_API_KEY", "gemini-2.5-flash"), ("NEXUS_DEEPSEEK_API_KEY", "deepseek-chat"),
    ("NEXUS_OPENROUTER_API_KEY", "openai/gpt-4.1-mini"),
)
MODEL_CATEGORIES = frozenset({"subscription", "unified", "direct", "local"})


@router.get("/ai-status")
async def ai_status(request: Request, context: READ) -> dict[str, object]:
    """Whether agents can call a model right now, and which one: drives the header status pill."""
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(ModelCredential).where(ModelCredential.status == "connected")
                                      .order_by(ModelCredential.is_default.desc(), ModelCredential.created_at))).all()
        budget = await session.get(TenantBudget, context.tenant_id)
    for row in rows:
        preset = PRESETS_BY_ID.get(row.preset_id or row.name)
        if preset is None or preset.category not in MODEL_CATEGORIES:
            continue
        chosen = row.default_models.get("orchestrator") or next((item for item in row.available_models if _is_chat_model(item)), "")
        if chosen:
            return {"ready": True, "model": chosen.split("/", 1)[-1], "source": "workspace", "provider": preset.name}
    if budget is not None and budget.remaining_usd > 0:
        for variable, model in PLATFORM_MODELS:
            if os.environ.get(variable):
                return {"ready": True, "model": model.split("/", 1)[-1], "source": "platform", "provider": "Server key"}
    return {"ready": False, "model": None, "source": None, "provider": None}


PLATFORM_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("NEXUS_OPENAI_API_KEY", "openai"), ("NEXUS_ANTHROPIC_API_KEY", "anthropic"), ("NEXUS_GEMINI_API_KEY", "gemini"),
    ("NEXUS_DEEPSEEK_API_KEY", "deepseek"), ("NEXUS_OPENROUTER_API_KEY", "openrouter"),
)


# Well-known models offered even when nothing is connected yet; each is usable once its provider has a key.
FLAGSHIP_MODELS: tuple[tuple[str, str, str], ...] = (
    ("openai", "gpt-5.4", "OpenAI"), ("openai", "gpt-4.1-mini", "OpenAI"),
    ("anthropic", "claude-sonnet-4-6", "Anthropic"), ("anthropic", "claude-opus-4-6", "Anthropic"),
    ("gemini", "gemini-2.5-pro", "Google Gemini"), ("gemini", "gemini-2.5-flash", "Google Gemini"),
    ("deepseek", "deepseek-chat", "DeepSeek"),
)


@router.get("/chat-models")
async def chat_models(request: Request, context: READ) -> dict[str, object]:
    """Every chat model this workspace can run right now, grouped by where it comes from, for the model selector.
    Ids are `provider/model`, the same names the Meta-Architect accepts as `preferred_model`."""
    from app.routers.architect import _approved_chat_models

    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(ModelCredential).where(ModelCredential.status == "connected")
                                      .order_by(ModelCredential.is_default.desc(), ModelCredential.created_at))).all()
        budget = await session.get(TenantBudget, context.tenant_id)
    entries: dict[str, dict[str, object]] = {}
    default: str | None = None

    def add(provider: str, model: str, group: str, source: str, local: bool, unverified: bool = False) -> None:
        identifier = f"{provider}/{model}"
        if identifier not in entries and _approved_chat_models({identifier}):
            entries[identifier] = {"id": identifier, "model": model, "provider": provider, "group": group, "source": source, "local": local, "unverified": unverified}

    for row in rows:
        preset = PRESETS_BY_ID.get(row.preset_id or row.name)
        if preset is None or preset.category not in MODEL_CATEGORIES:
            continue
        doubtful = suspect_models(row.settings)
        chosen = row.default_models.get("orchestrator") or next((item for item in row.available_models if _is_chat_model(item) and item not in doubtful), "")
        if chosen and default is None:
            default = f"{row.provider}/{chosen}"
        for model in row.available_models:
            if _is_chat_model(model):
                add(row.provider, model, preset.name, "workspace", preset.local, model in doubtful)
    if budget is not None and budget.remaining_usd > 0:
        for variable, provider in PLATFORM_PROVIDERS:
            if not os.environ.get(variable):
                continue
            preset_models = [model.id for preset in PRESETS if RUNTIME_PROVIDER.get(preset.id) == provider and preset.category == "direct"
                             for model in preset.models if model.kind == "chat"]
            fallback = next((model for key, model in PLATFORM_MODELS if key == variable), "")
            for model in dict.fromkeys([fallback.split("/", 1)[-1] if provider != "openrouter" else fallback, *preset_models]):
                if model:
                    add(provider, model, "Server key", "platform", False)
            if default is None and fallback:
                default = f"{provider}/{fallback if provider == 'openrouter' else fallback.split('/', 1)[-1]}"
    if default is not None and default not in entries:
        default = next(iter(entries), None)
    reachable = {str(item["provider"]) for item in entries.values()}
    suggested = [
        {"id": f"{provider}/{model}", "model": model, "provider": provider, "group": label, "connected": provider in reachable}
        for provider, model, label in FLAGSHIP_MODELS if f"{provider}/{model}" not in entries
    ]
    return {"models": list(entries.values()), "default": default, "suggested": suggested}


@router.get("/credentials", response_model=list[CredentialView])
async def list_credentials(request: Request, context: READ) -> list[CredentialView]:
    services = get_services(request)
    cipher = services._store()._cipher
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(ModelCredential).order_by(ModelCredential.created_at))).all()
        return [_view(row, cipher) for row in rows]


@router.post("/credentials", response_model=CredentialView, status_code=status.HTTP_201_CREATED)
async def save_credential(body: CredentialWrite, request: Request, context: BUILD) -> CredentialView:
    provider = _runtime_provider(body.preset_id)
    base_url = _base_url(body.preset_id, body.base_url)
    preset = PRESETS_BY_ID[body.preset_id]
    if body.preset_id == "custom_openai_gateway" and not body.base_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A base URL is required for a custom gateway")
    if body.base_url and not preset.local:
        await _resolve_public_url(body.base_url)
    services = get_services(request)
    cipher = services._store()._cipher
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(
            ModelCredential.tenant_id == context.tenant_id,
            ModelCredential.workspace_id == context.workspace_id,
            ModelCredential.provider == provider,
            ModelCredential.name == body.preset_id,
        ))
        if row is None:
            if body.api_key is None and not body.secrets and not preset.local:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A provider credential is required")
            row = ModelCredential(
                id=uuid4(),
                tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                provider=provider, name=body.preset_id, encrypted_key="", key_version=1,
            )
            session.add(row)
        secret_fields: dict[str, str] = {}
        if row.encrypted_key:
            previous = cipher.decode_fields(cipher.decrypt(row.encrypted_key, context.tenant_id, context.workspace_id, provider))
            secret_fields.update(previous)
        if body.api_key is not None:
            secret_fields["api_key"] = body.api_key.get_secret_value()
        secret_fields.update({name: value.get_secret_value() for name, value in body.secrets.items()})
        required_secret_names = {field.name for field in preset.auth_fields if field.required and field.secret}
        if not preset.local and not all(name in secret_fields for name in required_secret_names):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "All required provider credential fields must be set")
        required_settings = {field.name for field in preset.auth_fields if field.required and not field.secret and field.name != "base_url"}
        if not required_settings.issubset(body.settings):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "All required provider settings must be set")
        if preset.local and not secret_fields:
            secret_fields["api_key"] = "local-no-secret"
        serialized_fields = (
            next(iter(secret_fields.values()))
            if set(secret_fields) == {"api_key"}
            else cipher.encode_fields(secret_fields)
        )
        row.encrypted_key = cipher.encrypt(serialized_fields, context.tenant_id, context.workspace_id, provider)
        row.preset_id = body.preset_id
        row.base_url = base_url
        row.status = "untested"
        row.is_default = body.is_default
        model_names = [model.id for model in preset.models]
        custom_models = body.settings.get("custom_model_ids", "")
        if custom_models:
            model_names = [item.strip() for item in custom_models.split(",") if item.strip()]
        row.available_models = model_names
        row.default_models = body.default_models
        row.settings = cast(dict[str, object], body.settings)
        row.safe_error = None
        if body.is_default:
            await session.execute(update(ModelCredential).where(
                ModelCredential.tenant_id == context.tenant_id,
                ModelCredential.workspace_id == context.workspace_id,
                ModelCredential.provider == provider,
                ModelCredential.id != row.id,
            ).values(is_default=False))
        await session.flush()
        await session.refresh(row)
        return _view(row, cipher)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_credential(credential_id: UUID, request: Request, context: BUILD) -> Response:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id))
        if row is None:
            raise not_found("Provider credential was not found in this workspace")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/default-models")
async def get_default_models(request: Request, context: READ) -> dict[str, str]:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(ModelCredential).order_by(ModelCredential.is_default.desc(), ModelCredential.created_at))).all()
        for row in rows:
            if row.default_models:
                return row.default_models
    return {}


@router.put("/default-models")
async def set_default_models(values: dict[str, str], request: Request, context: BUILD) -> dict[str, str]:
    if len(values) > 16 or any(not key or len(key) > 80 or not value or len(value) > 250 for key, value in values.items()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Default model selection is invalid")
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(
            ModelCredential.tenant_id == context.tenant_id,
            ModelCredential.workspace_id == context.workspace_id,
        ).order_by(ModelCredential.is_default.desc(), ModelCredential.created_at).limit(1))
        if row is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Configure a provider before selecting default models")
        row.default_models = values
    return values


@dataclass(frozen=True)
class ModelDecision:
    available: list[str]
    suspects: list[str]
    unlisted: list[str]


def pinned_models(settings: Mapping[str, Any] | None) -> list[str]:
    """The model ids the user declared for this connection (`custom_model_ids`), in order, without repeats."""
    raw = str((settings or {}).get("custom_model_ids", ""))
    return list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))


def suspect_models(settings: Mapping[str, Any] | None) -> set[str]:
    """Models the last connection test saw refused twice; they are flagged in the picker and never chosen automatically."""
    return {item for item in str((settings or {}).get("suspect_models", "")).split(",") if item}


def decide_models(pinned: list[str], discovered: list[str], refused: set[str]) -> ModelDecision:
    """What a connection offers. The user's pin wins over the gateway's advertised list (a gateway lists everything it knows);
    models the test saw refused stay selectable but are flagged; pinned names the gateway does not list are reported."""
    available = list(pinned) if pinned else list(discovered)
    return ModelDecision(
        available=available,
        suspects=[model for model in available if model in refused],
        unlisted=[model for model in pinned if discovered and model not in discovered],
    )


# First pass is wide, later passes narrow: a gateway answers a burst with 429/503/timeouts, which says nothing about the model.
PROBE_PASSES = (24, 8, 4)
PROBE_BUDGET_SECONDS = 15.0
PROBE_TIMEOUT_SECONDS = 8.0
# Names of models that are not chat models; the chat endpoint says 404 for them, which says nothing about the account.
NOT_CHAT_PROBED = ("video", "imagine", "sora")
# A model the account is refused for good: it does not exist there, or the account has no access to it.
# Anything else (429, 5xx, a timeout, a 400 about parameters) does not prove the model is unusable.
REFUSED_FOR_GOOD = frozenset({403, 404})
THROTTLED = frozenset({429, 500, 502, 503, 504})


async def usable_models(client: httpx.AsyncClient, base_url: str, headers: dict[str, str], models: list[str],
                        deadline: float = PROBE_BUDGET_SECONDS, pause: float = 1.0) -> list[str]:
    """The listed models this key can really call. A gateway advertises every model it knows, some of which answer 404 or 403
    for this account; each chat model is asked for one token. A model is dropped only when it is refused twice: under a burst a
    gateway also answers 404 for models that work. Throttled or failed answers are asked again in a narrower pass. Models still
    undecided when the time budget ends stay listed, non-chat models are kept as listed, and the order is kept."""
    loop = asyncio.get_running_loop()
    stop = loop.time() + deadline
    refusals: dict[str, int] = {}
    pending = [model for model in models if _is_chat_model(model) and not any(part in model.lower() for part in NOT_CHAT_PROBED)]

    async def ask(model: str, gate: asyncio.Semaphore) -> str:
        """"refused", "usable" or "unknown"."""
        async with gate:
            if loop.time() >= stop:
                return "unknown"
            try:
                response = await client.post(f"{base_url}/chat/completions", headers=headers, timeout=PROBE_TIMEOUT_SECONDS,
                                             json={"model": model, "messages": [{"role": "user", "content": "OK"}], "max_tokens": 1})
            except httpx.HTTPError:
                return "unknown"
        if response.status_code in REFUSED_FOR_GOOD:
            return "refused"
        return "unknown" if response.status_code in THROTTLED else "usable"

    for width in PROBE_PASSES:
        if not pending or loop.time() >= stop:
            break
        gate = asyncio.Semaphore(width)
        verdicts = await asyncio.gather(*(ask(model, gate) for model in pending))
        undecided: list[str] = []
        for model, verdict in zip(pending, verdicts):
            if verdict == "refused":
                refusals[model] = refusals.get(model, 0) + 1
            elif verdict == "usable":
                refusals.pop(model, None)
                continue
            if refusals.get(model, 0) < 2:
                undecided.append(model)
        pending = undecided
        if pending and pause:
            await asyncio.sleep(pause)
    return [model for model in models if refusals.get(model, 0) < 2]


async def assess_models(preset_id: str, base_url: str, api_key: str, settings: Mapping[str, Any], discovered: list[str]) -> ModelDecision:
    """What a connection test concludes about the models: the user's pin (else the gateway's list), with the models the
    gateway refuses twice flagged. The probe is a soft signal for hosted OpenAI-compatible gateways; nothing is removed by it."""
    pinned = pinned_models(settings)
    preset = PRESETS_BY_ID[preset_id]
    refused: set[str] = set()
    if preset.protocol == "openai-compatible" and preset_id != "ollama" and not preset.local:
        checked = pinned or discovered
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False) as probe:
            refused = set(checked) - set(await usable_models(probe, base_url, {"Authorization": f"Bearer {api_key}"}, checked))
    return decide_models(pinned, discovered, refused)


async def _ping(preset_id: str, base_url: str, api_key: str, model: str | None) -> tuple[list[str], dict[str, object] | None]:
    preset = PRESETS_BY_ID[preset_id]
    discovered: list[str] = []
    balance: dict[str, object] | None = None
    timeout = httpx.Timeout(12.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        if preset_id == "ollama":
            host = base_url.removesuffix("/v1")
            response = await client.get(f"{host}/api/tags")
            response.raise_for_status()
            payload = response.json()
            discovered = [str(item["name"]) for item in payload.get("models", []) if isinstance(item, dict) and isinstance(item.get("name"), str)]
            if not discovered:
                raise ValueError("No locally available models were found")
        elif preset.protocol == "openai-compatible":
            model_name = model or next((item.id for item in preset.models if item.kind == "chat"), "")
            model_name = model_name.split("/", 1)[-1] if "/" in model_name else model_name
            headers = {"Authorization": f"Bearer {api_key}"}
            listing = await client.get(f"{base_url}/models", headers=headers)
            if listing.is_success:
                discovered = [str(item["id"]) for item in listing.json().get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
            if discovered and model_name not in discovered:
                # A third-party provider rarely serves our built-in default model; test with one it actually lists.
                model_name = next((item for item in discovered if _is_chat_model(item)), discovered[0])
            if model_name:
                if "embedding" in model_name:
                    response = await client.post(f"{base_url}/embeddings", headers=headers, json={"model": model_name, "input": "Nexus provider connectivity check"})
                else:
                    response = await client.post(f"{base_url}/chat/completions", headers=headers, json={"model": model_name, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 1})
                response.raise_for_status()
            elif not listing.is_success:
                listing.raise_for_status()
        elif preset.protocol == "anthropic":
            model_name = model or "claude-3-5-haiku-latest"
            response = await client.post(f"{base_url}/v1/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, json={"model": model_name, "max_tokens": 1, "messages": [{"role": "user", "content": "OK"}]})
            response.raise_for_status()
        elif preset.protocol == "gemini":
            model_name = model or "gemini-2.5-flash"
            model_name = model_name.split("/", 1)[-1]
            if "embedding" in model_name:
                response = await client.post(f"{base_url}/v1beta/models/{model_name}:embedContent", headers={"x-goog-api-key": api_key}, json={"content": {"parts": [{"text": "Nexus provider connectivity check"}]}})
            else:
                response = await client.post(f"{base_url}/v1beta/models/{model_name}:generateContent", headers={"x-goog-api-key": api_key}, json={"contents": [{"parts": [{"text": "OK"}]}], "generationConfig": {"maxOutputTokens": 1}})
            response.raise_for_status()
        elif preset_id == "serper":
            response = await client.post(f"{base_url}/search", headers={"X-API-KEY": api_key}, json={"q": "nexus provider connection check", "num": 1})
            response.raise_for_status()
        elif preset_id == "tavily":
            response = await client.post(f"{base_url}/search", json={"api_key": api_key, "query": "nexus provider connection check", "max_results": 1})
            response.raise_for_status()
        elif preset_id == "firecrawl":
            response = await client.post(f"{base_url}/scrape", headers={"Authorization": f"Bearer {api_key}"}, json={"url": "https://example.com", "formats": ["markdown"]})
            response.raise_for_status()
        elif preset_id == "elevenlabs":
            response = await client.get(f"{base_url}/user", headers={"xi-api-key": api_key})
            response.raise_for_status()
        elif preset_id == "composio":
            response = await client.get(f"{base_url}/tools", headers={"x-api-key": api_key})
            response.raise_for_status()
        elif preset_id == "tiktok":
            response = await client.get(f"{base_url}/v2/user/info/", params={"fields": "open_id"}, headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
        elif preset_id == "facebook":
            response = await client.get(f"{base_url}/me", params={"fields": "id,name"}, headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
        elif preset_id == "youtube":
            response = await client.get(f"{base_url}/channels", params={"part": "id", "mine": "true"}, headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
        elif preset_id == "daytona":
            response = await client.get(f"{base_url}/users/me", headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
        else:
            raise ValueError("Connectivity checks are not available for this credential type yet")
        if preset_id == "shopaikey" and urlsplit(base_url).hostname == "api.shopaikey.com":
            balance_response = await client.get("https://api.shopaikey.com/usage", params={"apiKey": api_key})
            if balance_response.is_success:
                data = balance_response.json()
                if isinstance(data, dict):
                    balance = {key: data[key] for key in ("balance", "remaining", "credits", "used", "usage", "currency") if key in data and isinstance(data[key], (str, int, float, bool))}
    return discovered, balance


@router.post("/credentials/{credential_id}/test")
async def test_credential(credential_id: UUID, request: Request, context: BUILD) -> dict[str, object]:
    services = get_services(request)
    cipher = services._store()._cipher
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id))
        if row is None:
            raise not_found("Provider credential was not found in this workspace")
        preset_id, provider, api_base, models, default_models, settings = row.preset_id or row.name, row.provider, row.base_url, row.available_models, row.default_models, dict(row.settings or {})
        encrypted_fields = cipher.decode_fields(cipher.decrypt(row.encrypted_key, context.tenant_id, context.workspace_id, provider))
        api_key = encrypted_fields.get("api_key") or next(iter(encrypted_fields.values()), "")
    start = datetime.now(timezone.utc)
    try:
        if api_base is None:
            api_base = PRESETS_BY_ID[preset_id].base_url or ""
        preset = PRESETS_BY_ID[preset_id]
        if not preset.local:
            await _resolve_public_url(api_base)
        ping_model = default_models.get("embedding") or default_models.get("orchestrator") or (models[0] if models else None)
        discovered, balance = await _ping(preset_id, api_base, api_key, ping_model)
        decision = await assess_models(preset_id, api_base, api_key, settings, discovered)
        result_status, safe_error = "connected", None
    except (httpx.HTTPError, ValueError, KeyError, OSError, json.JSONDecodeError):
        discovered, balance, decision = [], None, None
        result_status, safe_error = "error", "Connection test failed; verify the provider key, URL, and model selection."
    elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ModelCredential).where(ModelCredential.id == credential_id))
        if row is None:
            raise not_found("Provider credential was not found in this workspace")
        row.status = result_status
        row.last_tested_at = datetime.now(timezone.utc)
        row.safe_error = safe_error
        row.live_balance = balance
        if decision is not None and decision.available:
            row.available_models = decision.available
            kept = {key: value for key, value in dict(row.settings or {}).items() if key != "suspect_models"}
            row.settings = {**kept, **({"suspect_models": ",".join(decision.suspects)} if decision.suspects else {})}
    shown = decision.available if decision is not None and decision.available else models
    return {"credential_id": str(credential_id), "status": result_status.upper(), "latency_ms": elapsed_ms, "available_models": shown, "balance": balance, "error": safe_error,
            "suspect_models": decision.suspects if decision is not None else [], "unlisted_models": decision.unlisted if decision is not None else []}
