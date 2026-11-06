"""A model list the user pinned beats what the gateway advertises, and doubtful models are flagged, not hidden.

opencode never loads a provider's whole `/models` list for a custom provider: the user declares the models and the app shows
exactly those. Here the pin already existed at connect time, but the connection test then replaced it with the gateway's list."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.routers.architect import reachable_model_names
from app.routers.providers import decide_models, pinned_models, suspect_models


def test_pinned_models_are_read_from_the_comma_separated_setting() -> None:
    assert pinned_models({"custom_model_ids": " gpt-6-luna, claude-3-5-haiku ,, gpt-6-luna"}) == ["gpt-6-luna", "claude-3-5-haiku"]
    assert pinned_models({}) == [] and pinned_models(None) == []


def test_without_a_pin_the_gateway_list_is_shown_and_refused_models_are_flagged() -> None:
    result = decide_models([], ["a", "MiniMax-M2.5", "b"], {"MiniMax-M2.5"})
    assert result.available == ["a", "MiniMax-M2.5", "b"], "flagged models stay selectable"
    assert result.suspects == ["MiniMax-M2.5"] and result.unlisted == []


def test_a_pin_wins_over_the_gateway_list_and_names_the_gateway_does_not_list() -> None:
    result = decide_models(["gpt-6-luna", "typo-model"], ["gpt-6-luna", "other-1", "other-2"], set())
    assert result.available == ["gpt-6-luna", "typo-model"]
    assert result.unlisted == ["typo-model"] and result.suspects == []


def test_a_pinned_model_the_gateway_refuses_is_flagged() -> None:
    assert decide_models(["gpt-6-luna", "kimi-k3"], [], {"kimi-k3"}).suspects == ["kimi-k3"]


def test_an_empty_gateway_listing_does_not_call_every_pinned_name_unlisted() -> None:
    assert decide_models(["gpt-6-luna"], [], set()).unlisted == []


def test_suspects_are_read_back_from_the_stored_settings() -> None:
    assert suspect_models({"suspect_models": "a,b"}) == {"a", "b"}
    assert suspect_models({}) == set() and suspect_models(None) == set()


def test_the_architect_never_picks_a_flagged_model_by_itself() -> None:
    credential = SimpleNamespace(provider="openai", available_models=["gpt-6-luna", "MiniMax-M2.5"], settings={"suspect_models": "MiniMax-M2.5"}, id=uuid4())
    assert reachable_model_names({}, [credential], set()) == {"openai/gpt-6-luna"}


def _gateway(monkeypatch, refused: set[str]) -> list[str]:  # type: ignore[no-untyped-def]
    import json
    import httpx

    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        asked.append(model)
        return httpx.Response(404 if model in refused else 200, json={})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    return asked


def test_a_connection_test_with_a_pin_checks_only_the_pinned_models_and_flags_the_refused_one(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio
    from app.routers.providers import assess_models

    asked = _gateway(monkeypatch, {"kimi-k3"})
    listed = [f"model-{index}" for index in range(200)] + ["gpt-6-luna", "kimi-k3"]
    decision = asyncio.run(assess_models("shopaikey", "https://gateway.example/v1", "key", {"custom_model_ids": "gpt-6-luna, kimi-k3, spelled-wrong"}, listed))
    assert decision.available == ["gpt-6-luna", "kimi-k3", "spelled-wrong"]
    assert decision.suspects == ["kimi-k3"] and decision.unlisted == ["spelled-wrong"]
    assert set(asked) == {"gpt-6-luna", "kimi-k3", "spelled-wrong"}, "a pinned connection never probes the gateway's 200 other models"


def test_a_connection_test_without_a_pin_keeps_the_whole_list_and_flags_the_refused_models(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio
    from app.routers.providers import assess_models

    _gateway(monkeypatch, {"MiniMax-M2.5"})
    decision = asyncio.run(assess_models("shopaikey", "https://gateway.example/v1", "key", {}, ["MiniMax-M2.5", "gpt-6-luna"]))
    assert decision.available == ["MiniMax-M2.5", "gpt-6-luna"] and decision.suspects == ["MiniMax-M2.5"]
