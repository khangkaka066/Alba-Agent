from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from architect.clarify import (
    MAX_OPTIONS,
    MAX_QUESTIONS,
    ClarifyService,
    Decision,
    PlanOption,
    _Draft,
    clear_enough,
    decisions_block,
    normalise,
)


def _question(text: str, labels: tuple[str, ...] = ("Yes", "No"), marked: tuple[int, ...] = ()) -> dict[str, Any]:
    return {"text": text, "options": [{"label": label, "description": "", "recommended": index in marked} for index, label in enumerate(labels)]}


def _option(level: str, **extra: Any) -> dict[str, Any]:
    return {"summary": f"Build it as {level}", "level": level, "agents": 2, "speed": "fast", "tradeoffs": "", "recommended": False, "reason": "", **extra}


def test_questions_are_capped_deduplicated_and_each_has_exactly_one_recommendation() -> None:
    draft = _Draft(status="needs_input", questions=[
        _question("Which database should it use?", ("SQLite", "Postgres"), marked=(1, 0)),
        _question("Which database should it use?"),
        *[_question(f"Question number {number} here?") for number in range(6)],
    ])
    proposal = normalise(draft)
    assert len(proposal.questions) == MAX_QUESTIONS
    assert [q.text for q in proposal.questions].count("Which database should it use?") == 1
    for question in proposal.questions:
        assert sum(option.recommended for option in question.options) == 1
    first = proposal.questions[0]
    assert [option.recommended for option in first.options] == [True, False], "the first marked option wins when several are marked"


def test_a_question_with_fewer_than_two_options_or_no_options_list_is_dropped() -> None:
    proposal = normalise(_Draft(status="needs_input", questions=[
        _question("Only one choice here?", ("Only",)), {"text": "No options at all?"}, _question("A real question?"),
    ]))
    assert [q.text for q in proposal.questions] == ["A real question?"]


def test_options_need_distinct_levels_and_at_least_two_to_count_as_a_choice() -> None:
    same = normalise(_Draft(status="needs_input", options=[_option("solo"), _option("solo")], questions=[_question("Which output format?")]))
    assert same.options == [] and len(same.questions) == 1
    many = normalise(_Draft(status="needs_input", options=[_option("solo"), _option("team"), _option("studio", recommended=True)]))
    assert len(many.options) == MAX_OPTIONS and [o.recommended for o in many.options] == [False, False, True]
    unmarked = normalise(_Draft(status="needs_input", options=[_option("solo"), _option("team")]))
    assert [o.recommended for o in unmarked.options] == [True, False]


def test_nothing_to_ask_or_choose_means_ready() -> None:
    assert normalise(_Draft(status="needs_input")).status == "ready"
    assert normalise(_Draft(status="ready", questions=[_question("Which output format?")])).questions == []


def test_an_option_has_no_cost_field_and_one_that_carries_it_is_dropped() -> None:
    with pytest.raises(ValidationError):
        PlanOption.model_validate({**_option("solo"), "id": "a", "est_cost": "1 USD"})
    proposal = normalise(_Draft(status="needs_input", options=[_option("solo", est_cost="1 USD"), _option("team"), _option("studio")]))
    assert [o.level for o in proposal.options] == ["team", "studio"]


def test_detailed_requests_and_short_ones_about_supplied_files_skip_asking() -> None:
    assert clear_enough(" ".join(["word"] * 30), ())
    assert not clear_enough("make it better", ())
    assert clear_enough("fix the failing tests in this package and keep the public function names unchanged please", ("a.py",))
    assert not clear_enough("fix it", ("a.py",))


class _Generator:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.prompts: list[str] = []

    async def __call__(self, prompt: str, schema: type[BaseModel]) -> Any:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_a_clear_request_costs_no_model_call() -> None:
    generator = _Generator([])
    proposal = asyncio.run(ClarifyService(generator).propose(" ".join(["detail"] * 40)))
    assert proposal.status == "ready" and generator.prompts == []


def test_a_vague_request_asks_once_and_the_prompt_forbids_cost_and_redundant_questions() -> None:
    generator = _Generator([{"status": "needs_input", "assumptions": ["Python 3.11"], "questions": [_question("What should the report contain?", ("Summary", "Full detail"), marked=(0,))],
                             "options": [_option("solo"), _option("team", recommended=True)]}])
    proposal = asyncio.run(ClarifyService(generator).propose("make a report from the data", ("sales.csv",)))
    assert proposal.status == "needs_input" and proposal.assumptions == ["Python 3.11"]
    assert len(generator.prompts) == 1
    prompt = generator.prompts[0]
    assert "Do not mention cost" in prompt and "sales.csv" in prompt and "Never ask what the request or the file names already answer" in prompt


def test_an_invalid_card_is_retried_then_the_request_is_built_instead_of_blocked() -> None:
    generator = _Generator([{"status": "maybe"}, {"status": "maybe"}, {"status": "maybe"}])
    proposal = asyncio.run(ClarifyService(generator).propose("do something"))
    assert proposal.status == "ready" and len(generator.prompts) == 3
    assert "rejected" in generator.prompts[1]


def test_an_empty_request_is_refused() -> None:
    with pytest.raises(ValueError):
        asyncio.run(ClarifyService(_Generator([])).propose("   "))


def test_decisions_become_a_binding_block_and_nothing_is_added_when_there_are_none() -> None:
    block = decisions_block([Decision(question="Output format?", answer="CSV")], ["Python 3.11"])
    assert "binding" in block and "- Output format? -> CSV" in block and "Assumed (not answered): Python 3.11" in block
    assert decisions_block([], []) == ""


def test_the_propose_endpoint_is_registered_and_generate_accepts_decisions() -> None:
    from app.main import create_app
    from app.routers.architect import GenerateWorkflowRequest

    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert "/api/v1/architect/propose" in paths
    request = GenerateWorkflowRequest(user_requirement_prompt="Build a tool", decisions=[Decision(question="Format?", answer="CSV")],
                                      assumptions=["UTF-8"], plan_level="solo")
    assert request.plan_level == "solo" and request.decisions[0].answer == "CSV"
    assert GenerateWorkflowRequest(user_requirement_prompt="Build a tool").decisions == [], "automatic callers send no decisions and are unaffected"
    with pytest.raises(ValidationError):
        GenerateWorkflowRequest(user_requirement_prompt="x", plan_level="huge")  # type: ignore[arg-type]
