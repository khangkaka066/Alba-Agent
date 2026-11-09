"""Provider routing with conservative budget reservation and measured usage."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_UP
from importlib import import_module
from time import monotonic_ns
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol
from uuid import UUID

from .connection import effective_api_base
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["LITELLM_TELEMETRY_DISABLED"] = "true"
os.environ["LITELLM_OFFLINE_MODE"] = "true"

Provider = Literal["openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "groq", "mistral", "together_ai"]
BillingMode = Literal["platform", "byok"]
METERED = "METERED"
SUBSCRIPTION_INCLUDED = "SUBSCRIPTION_INCLUDED"
MICRO = Decimal("1000000")
MONEY = Decimal("0.00000001")


class BudgetExceeded(RuntimeError):
    """The tenant lacks credit for the requested maximum spend."""


@dataclass(frozen=True)
class ModelRate:
    prompt_usd_per_million: Decimal
    completion_usd_per_million: Decimal

    def __post_init__(self) -> None:
        if self.prompt_usd_per_million < 0 or self.completion_usd_per_million < 0:
            raise ValueError("Model rates must be nonnegative")

    def cost(self, prompt_tokens: int, completion_tokens: int, markup: Decimal) -> Decimal:
        if prompt_tokens < 0 or completion_tokens < 0 or markup < 1:
            raise ValueError("Invalid usage or markup")
        value = (
            Decimal(prompt_tokens) * self.prompt_usd_per_million
            + Decimal(completion_tokens) * self.completion_usd_per_million
        ) * markup / MICRO
        return value.quantize(MONEY, rounding=ROUND_UP)


ZERO_RATE = ModelRate(Decimal("0"), Decimal("0"))


@dataclass(frozen=True)
class ResolvedCredential:
    """What a call needs from a stored credential.

    ``wire="openai"`` means the endpoint speaks the OpenAI chat format for every model family
    (Copilot, subscription bridges), so Claude/Gemini model IDs are sent through the OpenAI client.
    """

    api_key: str
    api_base: str | None = None
    billing_mode: str = METERED
    headers: Mapping[str, str] = field(default_factory=dict)
    wire: Literal["native", "openai"] = "native"


def price_for(rates: Mapping[tuple[Provider, str], ModelRate], provider: Provider, model: str,
              credential: ResolvedCredential | None) -> tuple[ModelRate, str]:
    """Subscription credentials and unpriced models are free of per-token cost; priced models stay metered."""
    if credential is not None and credential.billing_mode == SUBSCRIPTION_INCLUDED:
        return ZERO_RATE, SUBSCRIPTION_INCLUDED
    rate = rates.get((provider, model))
    return (ZERO_RATE, SUBSCRIPTION_INCLUDED) if rate is None else (rate, METERED)


@dataclass(frozen=True)
class GatewayRequest:
    tenant_id: UUID
    workspace_id: UUID
    provider: Provider
    model: str
    messages: tuple[dict[str, str], ...]
    max_input_tokens: int
    max_output_tokens: int
    billing_mode: BillingMode
    agent_name: str
    workflow_id: UUID | None = None
    run_id: UUID | None = None
    credential_id: UUID | None = None
    api_base: str | None = None
    markup: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if not self.model or not self.messages or not self.agent_name:
            raise ValueError("Model, messages, and agent name are required")
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0 or self.markup < 1:
            raise ValueError("Token limits must be positive and markup must be at least 1")
        if self.api_base:
            from urllib.parse import urlsplit
            parsed = urlsplit(self.api_base)
            local = self.provider in ("ollama", "vllm") and parsed.scheme in ("http", "https")
            remote = parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            if not local and not remote:
                raise ValueError("Provider base URL must be an HTTPS endpoint")


@dataclass(frozen=True)
class UsageRecord:
    tenant_id: UUID
    workspace_id: UUID
    workflow_id: UUID | None
    run_id: UUID | None
    agent_name: str
    provider: Provider
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: Decimal
    latency_ms: int
    sandbox_compute_seconds: Decimal = Decimal("0")
    billing_mode: str = METERED


@dataclass(frozen=True)
class GatewayResult:
    content: str
    usage: UsageRecord
    usage_limit_exceeded: bool = False


class GatewayStore(Protocol):
    async def reserve(self, tenant_id: UUID, workspace_id: UUID, amount: Decimal) -> None: ...
    async def finalize(self, reserved: Decimal, usage: UsageRecord, charge_budget: bool) -> None: ...
    async def release(self, tenant_id: UUID, workspace_id: UUID, amount: Decimal) -> None: ...
    async def get_credential(self, tenant_id: UUID, workspace_id: UUID, credential_id: UUID, provider: Provider) -> str: ...


async def resolve_credential(store: Any, tenant_id: UUID, workspace_id: UUID, provider: Provider,
                             credential_id: UUID | None, model: str | None = None) -> ResolvedCredential | None:
    """Resolve through the richest method a store offers, so older stores that return plain keys keep working."""
    if credential_id:
        rich = getattr(store, "resolve_credential", None)
        if rich is not None:
            return await rich(tenant_id, workspace_id, credential_id, provider)  # type: ignore[no-any-return]
        details = getattr(store, "get_credential_details", None)
        if details is not None:
            key, base = await details(tenant_id, workspace_id, credential_id, provider)
            return ResolvedCredential(key, base)
        return ResolvedCredential(await store.get_credential(tenant_id, workspace_id, credential_id, provider))
    rich_model = getattr(store, "resolve_model_credential", None)
    if rich_model is not None and model is not None:
        return await rich_model(tenant_id, workspace_id, provider, model)  # type: ignore[no-any-return]
    rich_default = getattr(store, "resolve_default_credential", None)
    if rich_default is not None:
        return await rich_default(tenant_id, workspace_id, provider)  # type: ignore[no-any-return]
    legacy = getattr(store, "get_default_credential", None)
    if legacy is not None:
        pair = await legacy(tenant_id, workspace_id, provider)
        return ResolvedCredential(pair[0], pair[1]) if pair is not None else None
    return None


AsyncCompletion = Callable[..., Awaitable[Any]]
TokenCounter = Callable[[str, tuple[dict[str, str], ...]], int]


class LiteLLMRouter:
    def __init__(
        self,
        store: GatewayStore,
        rates: dict[tuple[Provider, str], ModelRate],
        completion: AsyncCompletion | None = None,
        token_counter: TokenCounter | None = None,
        allowed_local_bases: frozenset[str] = frozenset(),
    ) -> None:
        self._store = store
        self._rates = rates
        self._allowed_local_bases = allowed_local_bases
        if completion is None or token_counter is None:
            litellm = import_module("litellm")

            self._completion = completion or litellm.acompletion
            self._token_counter = token_counter or (lambda model, messages: int(litellm.token_counter(model=model, messages=list(messages))))
        else:
            self._completion = completion
            self._token_counter = token_counter

    @staticmethod
    def _model_name(provider: Provider, model: str, wire: str = "native") -> str:
        prefix = "openai" if wire == "openai" else "hosted_vllm" if provider == "vllm" else provider
        return f"{prefix}/{model}"

    async def complete(self, request: GatewayRequest) -> GatewayResult:
        credential = await resolve_credential(self._store, request.tenant_id, request.workspace_id, request.provider, request.credential_id, request.model)
        resolved_api_key = credential.api_key if credential else None
        rate, billing_mode = price_for(self._rates, request.provider, request.model, credential)
        model_name = self._model_name(request.provider, request.model, credential.wire if credential else "native")
        counted = self._token_counter(model_name, request.messages)
        if counted < 0 or counted > request.max_input_tokens:
            raise ValueError("Input exceeds the approved token limit")
        if request.billing_mode == "byok" and not resolved_api_key:
            raise ValueError("BYOK request has no configured workspace credential")
        effective_base = effective_api_base(request.provider, request.api_base, credential)
        if request.provider in ("ollama", "vllm") and effective_base not in self._allowed_local_bases:
            raise ValueError("Local provider URL is not approved by the server")
        reserved = rate.cost(request.max_input_tokens, request.max_output_tokens, request.markup)
        charge_budget = request.billing_mode == "platform" and resolved_api_key is None and reserved > 0
        if charge_budget:
            await self._store.reserve(request.tenant_id, request.workspace_id, reserved)
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": list(request.messages),
                "max_tokens": request.max_output_tokens,
            }
            if effective_base:
                kwargs["api_base"] = effective_base
            if resolved_api_key:
                kwargs["api_key"] = resolved_api_key
            if credential and credential.headers:
                kwargs["extra_headers"] = dict(credential.headers)
            started = monotonic_ns()
            response = await self._completion(**kwargs)
            latency_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            usage = response["usage"] if isinstance(response, dict) else response.usage
            prompt_tokens = int(usage["prompt_tokens"] if isinstance(usage, dict) else usage.prompt_tokens)
            completion_tokens = int(usage["completion_tokens"] if isinstance(usage, dict) else usage.completion_tokens)
            if prompt_tokens < 0 or completion_tokens < 0:
                raise ValueError("Provider returned negative token usage")
            usage_limit_exceeded = prompt_tokens > request.max_input_tokens or completion_tokens > request.max_output_tokens
            choices = response["choices"] if isinstance(response, dict) else response.choices
            first = choices[0]
            message = first["message"] if isinstance(first, dict) else first.message
            content = message["content"] if isinstance(message, dict) else message.content
            record = UsageRecord(
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                workflow_id=request.workflow_id,
                run_id=request.run_id,
                agent_name=request.agent_name,
                provider=request.provider,
                model=request.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost_usd=rate.cost(prompt_tokens, completion_tokens, request.markup),
                latency_ms=latency_ms,
                billing_mode=billing_mode,
            )
            await self._store.finalize(reserved if charge_budget else Decimal("0"), record, charge_budget)
            return GatewayResult(content=str(content or ""), usage=record, usage_limit_exceeded=usage_limit_exceeded)
        except BaseException:
            if charge_budget:
                await self._store.release(request.tenant_id, request.workspace_id, reserved)
            raise
