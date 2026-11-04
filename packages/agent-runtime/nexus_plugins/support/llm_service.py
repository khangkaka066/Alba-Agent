"""Model access for the whole runtime: one place that resolves credentials, prices usage and builds provider clients."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from autogen_core.models import ChatCompletionClient
from crewai import LLM
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import TenantBudget
from app.models.gateway_store import SqlGatewayStore
from app.models.scope import scoped_session
from nexus_model_gateway import CredentialCipher, LiteLLMEmbeddingRouter, LiteLLMRouter, ModelRate
from nexus_model_gateway.model_profiles import profile_for
from nexus_model_gateway.provider_presets import default_model_rates
from nexus_model_gateway.router import Provider

# Providers a bare "provider/model" name may refer to; anything else is treated as an OpenAI-style model id.
SUPPORTED_PROVIDERS = frozenset({"openai", "anthropic", "gemini", "deepseek", "openrouter", "groq", "mistral", "together_ai"})
_APPROVED_RATE_PROVIDERS = frozenset({"openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "groq", "mistral", "together_ai"})

_PLATFORM_ENVIRONMENT = (
    ("OPENAI", "OPENAI"), ("ANTHROPIC", "ANTHROPIC"), ("GEMINI", "GEMINI"), ("DEEPSEEK", "DEEPSEEK"),
    ("OPENROUTER", "OPENROUTER"), ("GROQ", "GROQ"), ("MISTRAL", "MISTRAL"), ("TOGETHER_AI", "TOGETHERAI"),
)
# The OpenAI and Anthropic SDKs read `<PROVIDER>_BASE_URL`, not litellm's `<PROVIDER>_API_BASE`. Without it, any call made
# through an SDK (for example NexusAI converting an answer into a Pydantic model) goes to the vendor's own host with the
# gateway's key and is rejected with 401.
_SDK_BASE_URL_PROVIDERS = frozenset({"OPENAI", "ANTHROPIC"})


def load_model_rates() -> dict[tuple[Provider, str], ModelRate]:
    source = os.environ.get("NEXUS_MODEL_RATES_JSON", "{}")
    if len(source) > 65_536:
        raise ValueError("Model price configuration is too large")
    raw = json.loads(source)
    if not isinstance(raw, dict):
        raise ValueError("Model price configuration must be an object")
    result: dict[tuple[Provider, str], ModelRate] = {
        (cast(Provider, provider), model): ModelRate(prompt, completion)
        for (provider, model), (prompt, completion) in default_model_rates().items()
    }
    for full_name, prices in raw.items():
        if not isinstance(full_name, str) or not isinstance(prices, dict):
            raise ValueError("Model price entry is invalid")
        provider, separator, model = full_name.partition("/")
        if provider not in _APPROVED_RATE_PROVIDERS or not separator or not model:
            raise ValueError("Model price key is invalid")
        result[(cast(Provider, provider), model)] = ModelRate(
            Decimal(str(prices["prompt_usd_per_million"])),
            Decimal(str(prices.get("completion_usd_per_million", "0"))),
        )
    return result


def local_model_bases() -> frozenset[str]:
    raw = os.environ.get("NEXUS_ALLOWED_LOCAL_MODEL_BASES_JSON", "[]")
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or any(not isinstance(base, str) or not base.startswith(("http://", "https://")) for base in parsed):
        raise ValueError("Allowed local model bases must be a JSON array of HTTP URLs")
    defaults = {
        "http://host.docker.internal:11434/v1",
        "http://host.docker.internal:1234/v1",
        "http://host.docker.internal:8000/v1",
    }
    return frozenset(base.rstrip("/") for base in parsed) | frozenset(defaults)


def configure_platform_model_keys() -> None:
    """Expose `NEXUS_<PROVIDER>_API_KEY/_API_BASE` to the provider libraries under their own variable names."""
    for nexus_part, library_part in _PLATFORM_ENVIRONMENT:
        for suffix in ("API_KEY", "API_BASE"):
            value = os.environ.get(f"NEXUS_{nexus_part}_{suffix}")
            if value:
                os.environ.setdefault(f"{library_part}_{suffix}", value)
                if suffix == "API_BASE" and library_part in _SDK_BASE_URL_PROVIDERS:
                    os.environ.setdefault(f"{library_part}_BASE_URL", value)


async def has_managed_model_credit(engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID) -> bool:
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        budget = await session.get(TenantBudget, tenant_id)
        return budget is not None and budget.remaining_usd > 0


def split_model(model: str) -> tuple[str, str]:
    """`provider/model` into its parts; a name without a supported provider prefix is an OpenAI-style model id."""
    provider_name, separator, model_name = model.partition("/")
    if not separator or provider_name not in SUPPORTED_PROVIDERS:
        return "openai", model
    return provider_name, model_name


class LlmService:
    """Credential resolution, routers and provider clients shared by every part of the runtime."""

    def __init__(
        self, engine: AsyncEngine, rates: dict[tuple[Provider, str], ModelRate], cipher: CredentialCipher | None = None,
        *, gateway: LiteLLMRouter | None = None, embeddings: LiteLLMEmbeddingRouter | None = None,
    ) -> None:
        self.engine = engine
        self.rates = rates
        self._cipher = cipher
        self._gateway = gateway
        self._embeddings = embeddings

    def store(self) -> SqlGatewayStore:
        if self._cipher is None:
            self._cipher = CredentialCipher.from_environment()
        return SqlGatewayStore(self.engine, self._cipher)

    def gateway(self) -> LiteLLMRouter:
        if self._gateway is None:
            self._gateway = LiteLLMRouter(self.store(), self.rates, allowed_local_bases=local_model_bases())
        return self._gateway

    def embeddings(self) -> LiteLLMEmbeddingRouter:
        if self._embeddings is None:
            self._embeddings = LiteLLMEmbeddingRouter(self.store(), self.rates, allowed_local_bases=local_model_bases())
        return self._embeddings

    async def nexusai_client(self, tenant_id: UUID, workspace_id: UUID, model: str) -> LLM | None:
        """The client NexusAI agents use, built from the workspace's default credential or the managed platform key."""
        provider_name, model_name = split_model(model)
        resolved = await self.store().resolve_default_credential(tenant_id, workspace_id, cast(Provider, provider_name))
        options: dict[str, Any] = {}
        api_key: str | None
        api_base: str | None
        if resolved is not None:
            api_key, api_base = resolved.api_key, resolved.api_base
            if resolved.headers:
                options["extra_headers"] = dict(resolved.headers)
            litellm_provider = "openai" if resolved.wire == "openai" else provider_name
        else:
            if not await has_managed_model_credit(self.engine, tenant_id, workspace_id):
                return None
            api_key = os.environ.get(f"NEXUS_{provider_name.upper()}_API_KEY")
            api_base = os.environ.get(f"NEXUS_{provider_name.upper()}_API_BASE")
            litellm_provider = provider_name
        if not api_key:
            return None
        options.update({"model": f"{litellm_provider}/{model_name}", "api_key": api_key})
        if api_base:
            options["base_url"] = api_base
        return LLM(**options)

    async def nexusgen_client(self, model: str, tenant_id: UUID, workspace_id: UUID) -> ChatCompletionClient:
        """The client NexusGen agents use. Provider traffic goes through the OpenAI-compatible wire."""
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        provider_name, model_name = split_model(model)
        default = await self.store().resolve_default_credential(tenant_id, workspace_id, cast(Provider, provider_name))
        if default is None and not await has_managed_model_credit(self.engine, tenant_id, workspace_id):
            raise ValueError("Managed model credit or a workspace provider key is required")
        key = default.api_key if default else os.environ.get("NEXUS_GEN_API_KEY") or os.environ.get(f"NEXUS_{provider_name.upper()}_API_KEY") or os.environ.get("NEXUS_OPENAI_API_KEY")
        if not key:
            raise RuntimeError("No tenant or platform model credential is configured")
        profile = profile_for(model_name)
        options: dict[str, Any] = {"model": model_name, "api_key": key, "timeout": profile.timeout_seconds, "max_retries": profile.max_retries}
        base_url = default.api_base if default else os.environ.get("NEXUS_GEN_API_BASE") or os.environ.get(f"NEXUS_{provider_name.upper()}_API_BASE")
        if base_url:
            options["base_url"] = base_url
        if default and default.headers:
            options["default_headers"] = dict(default.headers)
        try:
            return OpenAIChatCompletionClient(**options)
        except ValueError:
            # Model IDs from subscription gateways (Claude, Gemini, ...) are unknown to the OpenAI client's catalog.
            options["model_info"] = {"vision": False, "function_calling": True, "json_output": True, "family": "unknown", "structured_output": True}
            return OpenAIChatCompletionClient(**options)
