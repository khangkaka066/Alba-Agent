"""Scoped, metered embedding requests through the approved model gateway."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from time import monotonic_ns
from typing import Any, Awaitable, Callable
from uuid import UUID

from .router import BillingMode, GatewayStore, ModelRate, Provider, UsageRecord, price_for, resolve_credential

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["LITELLM_TELEMETRY_DISABLED"] = "true"
os.environ["LITELLM_OFFLINE_MODE"] = "true"

EmbeddingCall = Callable[..., Awaitable[Any]]
EmbeddingTokenCounter = Callable[[str, tuple[str, ...]], int]


@dataclass(frozen=True)
class EmbeddingRequest:
    tenant_id: UUID
    workspace_id: UUID
    provider: Provider
    model: str
    texts: tuple[str, ...]
    max_input_tokens: int
    billing_mode: BillingMode
    agent_name: str = "knowledge_embedding"
    workflow_id: UUID | None = None
    run_id: UUID | None = None
    credential_id: UUID | None = None
    api_base: str | None = None
    markup: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if not self.model or not self.texts or any(not text.strip() for text in self.texts):
            raise ValueError("Embedding model and nonempty texts are required")
        if self.max_input_tokens < 1 or self.markup < 1:
            raise ValueError("Embedding token limit and markup are invalid")
        if self.api_base:
            from urllib.parse import urlsplit
            parsed = urlsplit(self.api_base)
            local = self.provider in ("ollama", "vllm") and parsed.scheme in ("http", "https")
            remote = parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            if not local and not remote:
                raise ValueError("Embedding base URL must be an HTTPS endpoint")


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    usage: UsageRecord
    usage_limit_exceeded: bool = False


class LiteLLMEmbeddingRouter:
    def __init__(
        self,
        store: GatewayStore,
        rates: dict[tuple[Provider, str], ModelRate],
        embedding: EmbeddingCall | None = None,
        token_counter: EmbeddingTokenCounter | None = None,
        allowed_local_bases: frozenset[str] = frozenset(),
    ) -> None:
        self._store = store
        self._rates = rates
        self._allowed_local_bases = allowed_local_bases
        if embedding is None or token_counter is None:
            litellm = import_module("litellm")
            self._embedding = embedding or litellm.aembedding
            self._token_counter = token_counter or (
                lambda model, texts: sum(int(litellm.token_counter(model=model, text=text)) for text in texts)
            )
        else:
            self._embedding = embedding
            self._token_counter = token_counter

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        credential = await resolve_credential(self._store, request.tenant_id, request.workspace_id, request.provider, request.credential_id)
        resolved_api_key = credential.api_key if credential else None
        rate, billing_mode = price_for(self._rates, request.provider, request.model, credential)
        wire = credential.wire if credential else "native"
        model_name = f"{'openai' if wire == 'openai' else 'hosted_vllm' if request.provider == 'vllm' else request.provider}/{request.model}"
        counted = self._token_counter(model_name, request.texts)
        if counted < 0 or counted > request.max_input_tokens:
            raise ValueError("Embedding input exceeds the approved token limit")
        if request.billing_mode == "byok" and not resolved_api_key:
            raise ValueError("BYOK embedding has no configured workspace credential")
        effective_base = request.api_base or (credential.api_base if credential else None) or os.environ.get(f"NEXUS_{request.provider.upper()}_API_BASE")
        if request.provider in ("ollama", "vllm") and effective_base not in self._allowed_local_bases:
            raise ValueError("Local embedding URL is not approved by the server")
        reserved = rate.cost(request.max_input_tokens, 0, request.markup)
        charge_budget = request.billing_mode == "platform" and resolved_api_key is None and reserved > 0
        if charge_budget:
            await self._store.reserve(request.tenant_id, request.workspace_id, reserved)
        try:
            arguments: dict[str, Any] = {"model": model_name, "input": list(request.texts)}
            if effective_base:
                arguments["api_base"] = effective_base
            if resolved_api_key:
                arguments["api_key"] = resolved_api_key
            if credential and credential.headers:
                arguments["extra_headers"] = dict(credential.headers)
            started = monotonic_ns()
            response = await self._embedding(**arguments)
            latency_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            data = response["data"] if isinstance(response, dict) else response.data
            vectors = tuple(
                tuple(float(value) for value in (item["embedding"] if isinstance(item, dict) else item.embedding))
                for item in data
            )
            if len(vectors) != len(request.texts) or not vectors or not vectors[0]:
                raise ValueError("Embedding provider returned the wrong vector count")
            dimension = len(vectors[0])
            if any(len(vector) != dimension or any(not math.isfinite(value) for value in vector) for vector in vectors):
                raise ValueError("Embedding provider returned invalid vector values")
            usage = response["usage"] if isinstance(response, dict) else response.usage
            prompt_tokens = int(usage["prompt_tokens"] if isinstance(usage, dict) else usage.prompt_tokens)
            if prompt_tokens < 0:
                raise ValueError("Embedding provider returned negative token usage")
            record = UsageRecord(
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                workflow_id=request.workflow_id,
                run_id=request.run_id,
                agent_name=request.agent_name,
                provider=request.provider,
                model=request.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_cost_usd=rate.cost(prompt_tokens, 0, request.markup),
                latency_ms=latency_ms,
                billing_mode=billing_mode,
            )
            await self._store.finalize(reserved if charge_budget else Decimal("0"), record, charge_budget)
            return EmbeddingResult(vectors, record, prompt_tokens > request.max_input_tokens)
        except BaseException:
            if charge_budget:
                await self._store.release(request.tenant_id, request.workspace_id, reserved)
            raise
