"""A schema-breaking architect draft is repaired by showing the model its own validation errors."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from architect.team_generator import MetaArchitectService, _WorkflowDraft

STAGE = {"kind": "sandbox", "label": "Implement", "purpose": "Write the function"}
GOOD = {"name": "Parser team", "summary": "Builds and checks a parser", "stages": [STAGE]}
BAD = {**GOOD, "stages": [{**STAGE, "skill_ids": ["python"]}]}


def service(replies: list[dict[str, Any]], prompts: list[str]) -> MetaArchitectService:
    async def generate(prompt: str, _schema: type[BaseModel]) -> Any:
        prompts.append(prompt)
        return replies[len(prompts) - 1]

    return MetaArchitectService(generate)


def test_invalid_draft_is_repaired_with_the_validation_error_in_the_next_prompt() -> None:
    prompts: list[str] = []
    draft = asyncio.run(service([BAD, GOOD], prompts)._draft("Design it", _WorkflowDraft))
    assert draft.name == "Parser team" and len(prompts) == 2
    assert "skill_ids" in prompts[1] and "rejected by validation" in prompts[1]


def test_repair_gives_up_after_two_retries_with_the_validation_error() -> None:
    prompts: list[str] = []
    with pytest.raises(ValidationError):
        asyncio.run(service([BAD, BAD, BAD], prompts)._draft("Design it", _WorkflowDraft))
    assert len(prompts) == 3
