"""Structured output must go through the agent's own client, never a client rebuilt from the model name."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from crews.converter import LlmCallConverter


class Verdict(BaseModel):
    ok: bool
    note: str


class FakeLlm:
    """Carries its own connection settings (as nexusai's LLM does) and records every call."""

    base_url = "https://tenant-gateway.example/v1"

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[list[dict[str, str]]] = []

    def supports_function_calling(self) -> bool:
        return True  # the default converter would take its instructor path here

    def call(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.answers.pop(0)


def convert(llm: FakeLlm) -> BaseModel:
    return LlmCallConverter(text="all good", llm=llm, model=Verdict, instructions="Return JSON {ok, note}").to_pydantic()


def test_conversion_uses_the_llm_object_it_was_given() -> None:
    llm = FakeLlm(['{"ok": true, "note": "fine"}'])
    assert convert(llm) == Verdict(ok=True, note="fine")
    assert len(llm.calls) == 1
    assert llm.calls[0][0]["role"] == "system" and llm.calls[0][1]["content"] == "all good"


def test_json_wrapped_in_prose_or_a_fence_is_recovered() -> None:
    llm = FakeLlm(['Here you go:\n```json\n{"ok": false, "note": "late"}\n```'])
    assert convert(llm) == Verdict(ok=False, note="late")


def test_a_bad_answer_is_retried_then_reported() -> None:
    llm = FakeLlm(["not json", '{"ok": true, "note": "second try"}'])
    assert convert(llm) == Verdict(ok=True, note="second try")
    assert len(llm.calls) == 2
    failing = FakeLlm(["nope"] * 5)
    with pytest.raises(Exception, match="Failed to convert text into a Pydantic model"):
        convert(failing)


def test_builder_attaches_the_converter_to_every_structured_task() -> None:
    import inspect
    import crews.builder as builder

    assert "converter_cls=LlmCallConverter" in inspect.getsource(builder)
