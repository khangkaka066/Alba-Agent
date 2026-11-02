"""Subscription plan connectors: credential parsers, Copilot device login, session minting and zero-cost billing."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from decimal import Decimal
from typing import Any, Callable, cast
from uuid import uuid4

import httpx
import pytest

from nexus_model_gateway import GatewayRequest, LiteLLMEmbeddingRouter, LiteLLMRouter, ModelRate, ResolvedCredential, UsageRecord
from nexus_model_gateway.embeddings import EmbeddingRequest
from nexus_model_gateway.router import METERED, SUBSCRIPTION_INCLUDED, Provider, price_for
from nexus_model_gateway.subscription_connectors import (
    COPILOT_HEADERS, ConnectorError, CopilotTokenBroker, billing_for, credential_headers, parse_claude_credentials,
    parse_codex_auth, parse_copilot_apps, parse_gemini_credentials, poll_device_login, start_device_login,
)

Rates = dict[tuple[Provider, str], ModelRate]


def _jwt(claims: dict[str, Any]) -> str:
    def encode(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{encode({'alg': 'none'})}.{encode(claims)}.signature"


# --- parsers -------------------------------------------------------------------------------------------------------

def test_codex_auth_reads_plan_expiry_and_account() -> None:
    token = _jwt({"exp": time.time() + 3600, "https://api.openai.com/auth": {"chatgpt_plan_type": "plus", "chatgpt_account_id": "acct-1"}})
    imported = parse_codex_auth(json.dumps({"OPENAI_API_KEY": None, "tokens": {"access_token": token, "account_id": "acct-9"}}))
    assert imported.secrets == {"api_key": token}
    assert imported.settings == {"auth_kind": "oauth_token", "plan": "plus", "account_id": "acct-9"}
    assert imported.expires_at is not None
    assert credential_headers("openai_subscription", imported.settings, token) == {"chatgpt-account-id": "acct-9"}


def test_codex_auth_rejects_expired_empty_and_invalid_files() -> None:
    expired = _jwt({"exp": time.time() - 10})
    with pytest.raises(ConnectorError, match="expired"):
        parse_codex_auth(json.dumps({"tokens": {"access_token": expired}}))
    with pytest.raises(ConnectorError, match="codex login"):
        parse_codex_auth("{}")
    with pytest.raises(ConnectorError, match="valid JSON"):
        parse_codex_auth("{nope")
    assert parse_codex_auth(json.dumps({"OPENAI_API_KEY": "sk-key"})).settings["auth_kind"] == "api_key"
    assert parse_codex_auth("bridge-token-123").secrets == {"api_key": "bridge-token-123"}


def test_claude_credentials_accept_cli_file_and_setup_token() -> None:
    soon = int((time.time() + 600) * 1000)
    imported = parse_claude_credentials(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat01-abc", "expiresAt": soon, "subscriptionType": "max"}}))
    assert imported.settings == {"auth_kind": "oauth_token", "plan": "max"} and imported.secrets == {"api_key": "sk-ant-oat01-abc"}
    headers = credential_headers("claude_subscription", imported.settings, "sk-ant-oat01-abc")
    assert headers["Authorization"] == "Bearer sk-ant-oat01-abc" and "oauth" in headers["anthropic-beta"]
    assert parse_claude_credentials("sk-ant-oat01-xyz").secrets == {"api_key": "sk-ant-oat01-xyz"}
    with pytest.raises(ConnectorError, match="expired"):
        parse_claude_credentials(json.dumps({"claudeAiOauth": {"accessToken": "t", "expiresAt": 1000}}))
    with pytest.raises(ConnectorError):
        parse_claude_credentials("not a token")


def test_gemini_and_copilot_files() -> None:
    soon = int((time.time() + 600) * 1000)
    assert parse_gemini_credentials(json.dumps({"access_token": "ya29.token", "expiry_date": soon})).secrets == {"api_key": "ya29.token"}
    with pytest.raises(ConnectorError):
        parse_gemini_credentials(json.dumps({"refresh_token": "only"}))
    apps = json.dumps({"github.com:Iv1.abc": {"oauth_token": "gho_secret", "user": "someone"}})
    assert parse_copilot_apps(apps).secrets == {"oauth_token": "gho_secret"}
    with pytest.raises(ConnectorError):
        parse_copilot_apps(json.dumps({"gitlab.com": {"oauth_token": "x"}}))


def test_billing_mode_rules() -> None:
    assert billing_for("github_copilot", "device_flow", False) == SUBSCRIPTION_INCLUDED
    assert billing_for("claude_subscription", "oauth_token", False) == SUBSCRIPTION_INCLUDED
    assert billing_for("openai_subscription", "api_key", True) == SUBSCRIPTION_INCLUDED  # token of a subscription bridge
    assert billing_for("openai_subscription", "api_key", False) == METERED  # plain vendor API key is still billed per token
    assert billing_for("openai", "api_key", False) == METERED


# --- Copilot device login and session tokens ------------------------------------------------------------------------

def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.AsyncClient]:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_device_login_start_and_poll_states() -> None:
    seen: list[httpx.Request] = []
    states = iter([{"error": "authorization_pending"}, {"error": "slow_down", "interval": 10}, {"error": "expired_token"},
                   {"error": "access_denied"}, {"access_token": "gho_new", "token_type": "bearer"}])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/login/device/code":
            return httpx.Response(200, json={"device_code": "dc", "user_code": "WDJB-MJHT", "verification_uri": "https://github.com/login/device", "expires_in": 900, "interval": 5})
        return httpx.Response(200, json=next(states))

    async def check() -> None:
        device = await start_device_login(_factory(handler))
        assert (device.user_code, device.interval) == ("WDJB-MJHT", 5) and len(device.user_code.replace("-", "")) == 8
        results = [await poll_device_login("dc", _factory(handler)) for _ in range(5)]
        assert [item.status for item in results] == ["pending", "slow_down", "expired", "denied", "authorized"]
        assert results[1].interval == 10 and results[4].oauth_token == "gho_new"

    asyncio.run(check())
    assert b"client_id=" in seen[0].content and b"read%3Auser" in seen[0].content
    assert b"device_code=dc" in seen[1].content


def test_copilot_broker_mints_caches_and_refreshes() -> None:
    calls = {"count": 0}
    now = {"t": 1_000_000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.headers["authorization"] == "token gho_user" and request.headers["copilot-integration-id"] == "vscode-chat"
        return httpx.Response(200, json={"token": f"tid=session-{calls['count']}", "expires_at": now["t"] + 1800, "endpoints": {"api": "https://api.business.githubcopilot.com/"}})

    broker = CopilotTokenBroker(client_factory=_factory(handler), clock=lambda: now["t"])

    async def check() -> None:
        first = await broker.credential("gho_user")
        assert first.api_key == "tid=session-1" and first.api_base == "https://api.business.githubcopilot.com"
        assert first.billing_mode == SUBSCRIPTION_INCLUDED and first.wire == "openai" and first.headers["Editor-Version"] == COPILOT_HEADERS["Editor-Version"]
        assert (await broker.credential("gho_user")).api_key == "tid=session-1" and calls["count"] == 1  # cached
        now["t"] += 1700  # inside the refresh margin
        assert (await broker.credential("gho_user")).api_key == "tid=session-2"

    asyncio.run(check())


def test_copilot_without_plan_gives_a_clear_error() -> None:
    broker = CopilotTokenBroker(client_factory=_factory(lambda _request: httpx.Response(404, json={"message": "Not Found"})))
    with pytest.raises(ConnectorError, match="active Copilot plan"):
        asyncio.run(broker.credential("gho_none"))


# --- billing: missing rates never fail a run -------------------------------------------------------------------------

class _Store:
    def __init__(self, credential: ResolvedCredential | None) -> None:
        self.credential = credential
        self.reserved = 0
        self.finalized: list[UsageRecord] = []

    async def reserve(self, *_args: object) -> None:
        self.reserved += 1

    async def finalize(self, _reserved: Decimal, usage: UsageRecord, _charge: bool) -> None:
        self.finalized.append(usage)

    async def release(self, *_args: object) -> None:
        return None

    async def get_credential(self, *_args: object) -> str:
        raise AssertionError("not used")

    async def resolve_default_credential(self, *_args: object) -> ResolvedCredential | None:
        return self.credential


def _request(provider: str, model: str, mode: str = "platform") -> GatewayRequest:
    return GatewayRequest(uuid4(), uuid4(), cast(Provider, provider), model, ({"role": "user", "content": "hi"},), 20, 5, cast(Any, mode), "agent")


async def _ok(**_kwargs: Any) -> dict[str, Any]:
    return {"usage": {"prompt_tokens": 100, "completion_tokens": 50}, "choices": [{"message": {"content": "ok"}}]}


def test_price_policy() -> None:
    rates: Rates = {("openai", "gpt-4.1-mini"): ModelRate(Decimal("0.4"), Decimal("1.6"))}
    subscription = ResolvedCredential("k", None, SUBSCRIPTION_INCLUDED)
    assert price_for(rates, "openai", "gpt-4.1-mini", None)[1] == METERED
    assert price_for(rates, "openai", "gpt-4.1-mini", subscription) == (ModelRate(Decimal("0"), Decimal("0")), SUBSCRIPTION_INCLUDED)
    assert price_for(rates, "openai", "never-heard-of-it", None)[1] == SUBSCRIPTION_INCLUDED
    assert price_for({}, "anthropic", "claude-opus-4-6", None)[0].cost(1_000_000, 1_000_000, Decimal("1")) == 0


def test_unpriced_model_runs_at_zero_cost_without_touching_the_budget() -> None:
    store = _Store(None)

    async def check() -> None:
        router = LiteLLMRouter(store, {}, completion=_ok, token_counter=lambda _m, _x: 5)
        result = await router.complete(_request("openai", "gpt-5.4"))
        assert result.usage.total_cost_usd == 0 and result.usage.billing_mode == SUBSCRIPTION_INCLUDED

    asyncio.run(check())
    assert store.reserved == 0


def test_priced_model_on_a_subscription_credential_costs_nothing_and_sends_gateway_headers() -> None:
    captured: dict[str, Any] = {}

    async def complete(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return await _ok()

    credential = ResolvedCredential("tid=session", "https://api.githubcopilot.com", SUBSCRIPTION_INCLUDED, dict(COPILOT_HEADERS), "openai")
    store = _Store(credential)
    rates: Rates = {("anthropic", "claude-sonnet-4"): ModelRate(Decimal("3"), Decimal("15"))}

    async def check() -> None:
        router = LiteLLMRouter(store, rates, completion=complete, token_counter=lambda _m, _x: 5)
        result = await router.complete(_request("anthropic", "claude-sonnet-4", "byok"))
        assert result.usage.total_cost_usd == 0 and result.usage.billing_mode == SUBSCRIPTION_INCLUDED

    asyncio.run(check())
    assert captured["model"] == "openai/claude-sonnet-4"  # Copilot speaks the OpenAI format for every model family
    assert captured["api_base"] == "https://api.githubcopilot.com" and captured["api_key"] == "tid=session"
    assert captured["extra_headers"]["Copilot-Integration-Id"] == "vscode-chat"


def test_metered_credential_keeps_price_and_native_provider() -> None:
    captured: dict[str, Any] = {}

    async def complete(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return await _ok()

    store = _Store(ResolvedCredential("sk-key", None))
    rates: Rates = {("openai", "gpt-4.1-mini"): ModelRate(Decimal("0.4"), Decimal("1.6"))}

    async def check() -> None:
        router = LiteLLMRouter(store, rates, completion=complete, token_counter=lambda _m, _x: 5)
        result = await router.complete(_request("openai", "gpt-4.1-mini"))
        assert result.usage.total_cost_usd > 0 and result.usage.billing_mode == METERED

    asyncio.run(check())
    assert captured["model"] == "openai/gpt-4.1-mini" and "extra_headers" not in captured


def test_embeddings_without_a_rate_do_not_fail() -> None:
    store = _Store(None)

    async def embed(**_kwargs: Any) -> dict[str, Any]:
        return {"data": [{"embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 3}}

    async def check() -> None:
        router = LiteLLMEmbeddingRouter(store, {}, embedding=embed, token_counter=lambda _m, _t: 3)
        result = await router.embed(EmbeddingRequest(uuid4(), uuid4(), "openai", "brand-new-embedder", ("hello",), 50, "platform", "kb"))
        assert result.usage.total_cost_usd == 0 and result.usage.billing_mode == SUBSCRIPTION_INCLUDED

    asyncio.run(check())
