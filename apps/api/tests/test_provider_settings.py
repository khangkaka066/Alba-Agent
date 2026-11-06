from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from nexus_plugins.support.llm_service import load_model_rates as _rates
from nexus_model_gateway import CredentialCipher, GatewayRequest, LiteLLMRouter, ModelRate
from nexus_model_gateway.provider_presets import PRESETS_BY_ID, default_model_rates


def test_provider_catalog_groups_and_shop_key_presets() -> None:
    assert {preset.category for preset in PRESETS_BY_ID.values()} == {"subscription", "unified", "direct", "local", "media", "tools", "channel"}
    shop = PRESETS_BY_ID["shopaikey"]
    assert shop.base_url == "https://api.shopaikey.com/v1"
    assert shop.anthropic_base_url == "https://api.shopaikey.com"
    assert shop.google_base_url == "https://api.shopaikey.com"
    assert shop.balance_url_template == "https://api.shopaikey.com/usage?apiKey={api_key}"
    assert default_model_rates()[("openai", "text-embedding-3-small")] == (Decimal("0.02"), Decimal("0"))


def test_credential_cipher_encrypts_and_scopes_saved_keys() -> None:
    tenant, workspace = uuid4(), uuid4()
    cipher = CredentialCipher(b"z" * 32)
    encrypted = cipher.encrypt("sk-private-value", tenant, workspace, "openai")
    assert "sk-private-value" not in encrypted
    assert cipher.decrypt(encrypted, tenant, workspace, "openai") == "sk-private-value"
    with pytest.raises(Exception):
        cipher.decrypt(encrypted, uuid4(), workspace, "openai")
    bundle = cipher.encrypt(cipher.encode_fields({"api_key": "sk-main", "client_secret": "secret-value"}), tenant, workspace, "pipedream")
    opened = cipher.decode_fields(cipher.decrypt(bundle, tenant, workspace, "pipedream"))
    assert opened == {"api_key": "sk-main", "client_secret": "secret-value"}


def test_rates_include_builtins_and_allow_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_MODEL_RATES_JSON", '{"openai/gpt-4.1-mini":{"prompt_usd_per_million":"0.5","completion_usd_per_million":"2"}}')
    rates = _rates()
    assert rates[("openai", "gpt-4.1-mini")] == ModelRate(Decimal("0.5"), Decimal("2"))
    assert rates[("openai", "text-embedding-3-small")] == ModelRate(Decimal("0.02"), Decimal("0"))


def test_shop_key_compatible_base_url_is_forwarded() -> None:
    class Store:
        async def reserve(self, *_args: object) -> None:
            return None
        async def finalize(self, *_args: object) -> None:
            return None
        async def release(self, *_args: object) -> None:
            return None
        async def get_credential(self, *_args: object) -> str:
            return "sk-test-secret"

    captured: dict[str, object] = {}

    async def complete(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"usage": {"prompt_tokens": 2, "completion_tokens": 1}, "choices": [{"message": {"content": "ok"}}]}

    async def check() -> None:
        router = LiteLLMRouter(Store(), {("openai", "gpt-4.1-mini"): ModelRate(Decimal("0.4"), Decimal("1.6"))}, completion=complete, token_counter=lambda _model, _messages: 2)
        result = await router.complete(GatewayRequest(
            uuid4(), uuid4(), "openai", "gpt-4.1-mini", ({"role": "user", "content": "hi"},),
            20, 5, "byok", "settings-test", credential_id=uuid4(), api_base="https://api.shopaikey.com/v1",
        ))
        assert result.content == "ok"

    asyncio.run(check())
    assert captured["api_base"] == "https://api.shopaikey.com/v1"
    assert captured["api_key"] == "sk-test-secret"


def test_active_workspace_credential_precedes_platform_budget_and_key() -> None:
    class Store:
        reserved = False
        async def reserve(self, *_args: object) -> None:
            self.reserved = True
        async def finalize(self, *_args: object) -> None:
            return None
        async def release(self, *_args: object) -> None:
            return None
        async def get_credential(self, *_args: object) -> str:
            raise AssertionError("No explicit credential ID is expected")
        async def get_default_credential(self, *_args: object) -> tuple[str, str]:
            return "sk-workspace-key", "https://api.shopaikey.com/v1"

    store = Store()
    captured: dict[str, object] = {}

    async def complete(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"usage": {"prompt_tokens": 1, "completion_tokens": 1}, "choices": [{"message": {"content": "ok"}}]}

    async def check() -> None:
        router = LiteLLMRouter(store, {("openai", "model"): ModelRate(Decimal("1"), Decimal("2"))}, completion=complete, token_counter=lambda _model, _messages: 1)
        await router.complete(GatewayRequest(
            uuid4(), uuid4(), "openai", "model", ({"role": "user", "content": "hi"},),
            10, 4, "platform", "tenant-key-test",
        ))

    asyncio.run(check())
    assert captured["api_key"] == "sk-workspace-key"
    assert captured["api_base"] == "https://api.shopaikey.com/v1"
    assert not store.reserved


def test_third_party_provider_is_tested_with_a_model_it_actually_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as jsonlib

    import httpx
    from app.routers import providers

    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "vendor-embed-1"}, {"id": "vendor-chat-1"}, {"id": "vendor-chat-2"}]})
        asked.append(jsonlib.loads(request.content)["model"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))  # providers uses the same module object
    models, _ = asyncio.run(providers._ping("shopaikey", "https://gateway.example/v1", "key", None))
    assert models == ["vendor-embed-1", "vendor-chat-1", "vendor-chat-2"]
    assert set(asked) == {"vendor-chat-1", "vendor-chat-2"}, "only models the provider lists are asked (the built-in default is not), and embeddings are skipped"
    assert PRESETS_BY_ID["shopaikey"].name == "Nexus Harness"
