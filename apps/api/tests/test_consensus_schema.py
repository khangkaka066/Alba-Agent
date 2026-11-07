"""Consensus mode must find the output schema of an architect-generated crew, not only registered ones.

The architect describes each task's output as JSON (`output_schema_json`) and names it `Architect_<stage>_<n>Output`.
Those names never exist in the registered schema table, so looking one up by name raised
`KeyError: 'Architect_crew_1_3Output'` at the end of a consensus node."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import BaseModel

from app.services import AppServices, NexusTextResult
from nexus_core_schema.models import TaskSpec


def _architect_task() -> TaskSpec:
    name = "Architect_crew_1_3Output"
    return TaskSpec(
        id="crew_1_task_3", agent_id="agent", description="Write the module", expected_output="A summary",
        output_schema=name,
        output_schema_json={"type": "object", "properties": {"summary": {"type": "string"}, "confidence": {"type": "number"}}, "required": ["summary"]},
    )


def _services() -> AppServices:
    from crews.builder import CrewBuilder
    stand_in = SimpleNamespace(output_schemas={"NexusTextResult": NexusTextResult})
    stand_in.crew_builder = lambda: CrewBuilder(stand_in.output_schemas)
    return cast(AppServices, stand_in)


def test_generated_schema_resolves_for_consensus() -> None:
    schema = AppServices.consensus_schema(_services(), _architect_task())
    assert issubclass(schema, BaseModel)
    assert schema.model_validate({"summary": "done"}).model_dump(mode="json") == {"summary": "done", "confidence": None}


def test_registered_schema_still_resolves() -> None:
    task = TaskSpec(id="t", agent_id="a", description="d", expected_output="e", output_schema="NexusTextResult")
    assert AppServices.consensus_schema(_services(), task) is NexusTextResult


def test_unknown_schema_name_is_a_clear_error_not_a_key_error() -> None:
    task = TaskSpec(id="t", agent_id="a", description="d", expected_output="e", output_schema="Nope")
    with pytest.raises(ValueError, match="Nope"):
        AppServices.consensus_schema(_services(), task)


def test_old_lookup_failed_on_generated_names() -> None:
    """The registry alone cannot answer for a generated name; this is the lookup that used to run."""
    registry: dict[str, Any] = {"NexusTextResult": NexusTextResult}
    with pytest.raises(KeyError, match="Architect_crew_1_3Output"):
        registry[_architect_task().output_schema]
