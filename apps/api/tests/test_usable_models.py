"""Connecting a provider must list only the models the key or subscription can actually call.

A gateway advertises every model it knows (232 for one third-party gateway), and some of them answer 404 or 403 for this
account. Showing them lets a user, and the architect's fallback, pick a model that can never run."""

from __future__ import annotations

import asyncio
import json

import httpx

from app.routers.providers import usable_models

BASE = "https://gateway.example/v1"


def _client(answers: dict[str, int | list[int]], seen: list[str] | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        if seen is not None:
            seen.append(model)
        answer = answers.get(model, 200)
        status = (answer.pop(0) if len(answer) > 1 else answer[0]) if isinstance(answer, list) else answer
        if status == -1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(status, json={"error": {"message": "x"}} if status >= 400 else {"choices": []})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _run(models: list[str], answers: dict[str, int | list[int]], seen: list[str] | None = None, **limits: float) -> list[str]:
    async def go() -> list[str]:
        async with _client(answers, seen) as client:
            return await usable_models(client, BASE, {"Authorization": "Bearer k"}, models, pause=0, **limits)
    return asyncio.run(go())


def test_models_the_account_cannot_call_are_dropped_and_order_is_kept() -> None:
    models = ["MiniMax-M2.5", "claude-3-5-haiku", "gpt-6-luna", "locked-model"]
    assert _run(models, {"MiniMax-M2.5": 404, "locked-model": 403}) == ["claude-3-5-haiku", "gpt-6-luna"]


def test_a_busy_slow_or_picky_model_is_kept_because_it_is_not_proven_unusable() -> None:
    models = ["rate-limited", "down", "slow", "wants-other-params", "gone"]
    answers: dict[str, int | list[int]] = {"rate-limited": 429, "down": 503, "slow": -1, "wants-other-params": 400, "gone": 404}
    assert _run(models, answers) == ["rate-limited", "down", "slow", "wants-other-params"]


def test_only_chat_models_are_probed_the_rest_are_kept_as_listed() -> None:
    seen: list[str] = []
    models = ["text-embedding-3-small", "whisper-1", "gpt-6-luna"]
    assert _run(models, {"text-embedding-3-small": 404}, seen) == models
    assert seen == ["gpt-6-luna"]


def test_every_model_is_probed_once() -> None:
    seen: list[str] = []
    models = [f"model-{index}" for index in range(100)]
    assert _run(models, {}, seen) == models and sorted(seen) == sorted(models)


def test_video_and_image_models_are_not_judged_by_the_chat_endpoint() -> None:
    models = ["grok-video-3", "grok-imagine-video-1.5", "gpt-6-luna"]
    assert _run(models, {"grok-video-3": 404, "grok-imagine-video-1.5": 404}) == models


def test_a_throttled_answer_is_asked_again_and_the_later_answer_decides() -> None:
    answers: dict[str, int | list[int]] = {"hidden-404": [404, 429, 404], "fine": [429, 200]}
    assert _run(["hidden-404", "fine"], answers) == ["fine"]


def test_one_refusal_is_not_enough_a_model_that_answers_404_under_load_but_works_is_kept() -> None:
    assert _run(["flaky", "gone"], {"flaky": [404, 200], "gone": 404}) == ["flaky"]


def test_a_single_refusal_followed_by_silence_keeps_the_model() -> None:
    assert _run(["maybe"], {"maybe": [404, 429, 429, 429]}) == ["maybe"]


def test_when_the_time_runs_out_the_undecided_models_stay_listed() -> None:
    assert _run(["a", "b"], {"a": 429, "b": 404}, deadline=0) == ["a", "b"]
