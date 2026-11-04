"""Ask a few targeted questions and propose options with a recommendation, before a team is built.

Asking is opt-in and separate from building: automatic callers (service keys, scripts) never wait for an answer. A request
that is already clear returns `ready` and nothing is asked. The limits below are enforced here, not left to the prompt, so a
model that over-asks or recommends nothing still produces a card a person can answer in one click.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from architect.adaptive import assess

MAX_QUESTIONS = 4
MAX_OPTIONS = 3
CLEAR_WORDS = 30  # a request this detailed is not worth interrupting
CLEAR_WORDS_WITH_FILES = 12

Level = Literal["solo", "team", "studio"]
Speed = Literal["fast", "medium", "slow"]
JsonGenerator = Callable[[str, type[BaseModel]], Awaitable[Any]]


class AnswerChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    recommended: bool = False


class ClarifyQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=5, max_length=300)
    options: list[AnswerChoice] = Field(min_length=2, max_length=4)
    allow_other: bool = True


class PlanOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    level: Level
    summary: str = Field(min_length=5, max_length=400)
    agents: int = Field(ge=1, le=60)
    speed: Speed
    tradeoffs: str = Field(default="", max_length=500)
    recommended: bool = False
    reason: str = Field(default="", max_length=400)


class PlanProposal(BaseModel):
    """`ready` means build now; `needs_input` carries what to ask and what to choose between."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "needs_input"]
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    questions: list[ClarifyQuestion] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    options: list[PlanOption] = Field(default_factory=list, max_length=MAX_OPTIONS)


class _Draft(BaseModel):
    """What the model returns; looser than the proposal, then normalised."""

    model_config = ConfigDict(extra="ignore")
    status: Literal["ready", "needs_input"] = "ready"
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    questions: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    options: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


def _slug(value: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:40] or fallback


def _one_recommended(items: list[Any]) -> None:
    """Exactly one item carries the recommendation: keep the first the model marked, or the first item."""
    marked = [item for item in items if item.recommended]
    keep = marked[0] if marked else items[0]
    for item in items:
        item.recommended = item is keep


def normalise(draft: _Draft) -> PlanProposal:
    """Enforce the limits: drop malformed or duplicate entries, cap counts, make the recommendation unambiguous."""
    questions: list[ClarifyQuestion] = []
    seen: set[str] = set()
    for index, raw in enumerate(draft.questions):
        if not isinstance(raw.get("options"), list):
            continue
        try:
            raw_id = _slug(str(raw.get("id") or raw.get("text") or ""), f"question_{index + 1}")
            question = ClarifyQuestion.model_validate({**raw, "id": raw_id, "options": raw["options"][:4]})
        except ValidationError:
            continue
        key = re.sub(r"\W+", " ", question.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        _one_recommended(question.options)
        questions.append(question)
        if len(questions) == MAX_QUESTIONS:
            break
    options: list[PlanOption] = []
    levels: set[str] = set()
    for index, raw in enumerate(draft.options):
        try:
            option = PlanOption.model_validate({**raw, "id": _slug(str(raw.get("id") or raw.get("summary") or ""), f"option_{index + 1}")})
        except ValidationError:
            continue
        if option.level in levels:  # two options of the same size are not a choice
            continue
        levels.add(option.level)
        options.append(option)
        if len(options) == MAX_OPTIONS:
            break
    if len(options) < 2:
        options = []  # one option is not a choice; the questions still stand on their own
    else:
        _one_recommended(options)
    if draft.status == "ready" or not (questions or options):
        return PlanProposal(status="ready", assumptions=[item[:300] for item in draft.assumptions[:6]])
    return PlanProposal(status="needs_input", assumptions=[item[:300] for item in draft.assumptions[:6]], questions=questions, options=options)


def clear_enough(prompt: str, input_file_names: Sequence[str]) -> bool:
    """A detailed request, or a short one about files that were supplied, is built without asking."""
    words = len(prompt.split())
    return words >= CLEAR_WORDS or (bool(input_file_names) and words >= CLEAR_WORDS_WITH_FILES)


_INSTRUCTIONS = (
    "You decide whether to interrupt a person before building an agent team for their request, and how.\n"
    "Ask a question ONLY if its answer would change what gets built. Never ask what the request or the file names already answer, "
    f"and never ask more than {MAX_QUESTIONS} questions. If nothing needs asking, return status \"ready\" with empty lists.\n"
    "Each question has 2-4 concrete options; mark exactly one \"recommended\": true, the one you would pick if the person said 'you choose'.\n"
    f"Also offer 2-{MAX_OPTIONS} ways to build it, each with a different level: \"solo\" (one coder and reviewer, for plain code or calculation work), "
    "\"team\" (a planned sequence of specialists), \"studio\" (departments with a quality gate, for large products). Say honestly what each "
    "gives up. Mark exactly one option recommended and give the reason. Use only these speeds: fast, medium, slow. Do not mention cost.\n"
    "Return JSON: {\"status\", \"assumptions\": [short strings you will assume if nobody answers], "
    "\"questions\": [{\"id\", \"text\", \"options\": [{\"label\", \"description\", \"recommended\"}]}], "
    "\"options\": [{\"id\", \"level\", \"summary\", \"agents\", \"speed\", \"tradeoffs\", \"recommended\", \"reason\"}]}."
)


class ClarifyService:
    def __init__(self, json_generator: JsonGenerator) -> None:
        self._generate_json = json_generator

    async def propose(self, prompt: str, input_file_names: Sequence[str] = ()) -> PlanProposal:
        text = prompt.strip()
        if not text or len(text) > 12_000:
            raise ValueError("Requirement prompt must contain 1 to 12,000 characters")
        if clear_enough(text, input_file_names):
            return PlanProposal(status="ready")
        hint = assess(text, input_file_names)
        payload = json.dumps({"request": text, "input_files": list(input_file_names)[:40],
                              "light_path_fits": hint.level == "solo", "why": hint.reason}, ensure_ascii=False)
        problem = ""
        for _ in range(3):
            asked = f"{_INSTRUCTIONS}\n\n{payload}" + (f"\n\nYour previous JSON was rejected: {problem}\nReturn the corrected JSON only." if problem else "")
            try:
                return normalise(_Draft.model_validate(await self._generate_json(asked, _Draft)))
            except ValidationError as error:
                problem = "; ".join(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()[:6])
        return PlanProposal(status="ready")  # asking is a courtesy: when the model cannot produce a valid card, build instead of blocking


class Decision(BaseModel):
    """One answered question, sent back by the client when it asks for the team to be built."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=300)


def decisions_block(decisions: Sequence[Decision], assumptions: Sequence[str]) -> str:
    """The text appended to the requirement so the architect treats the person's choices as binding."""
    lines = [f"- {item.question.strip()} -> {item.answer.strip()}" for item in decisions]
    lines.extend(f"- Assumed (not answered): {item.strip()[:300]}" for item in assumptions if item.strip())
    if not lines:
        return ""
    return "\n\nDecisions made with the user (binding; do not contradict them):\n" + "\n".join(lines)
