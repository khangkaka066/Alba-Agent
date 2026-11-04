"""Structured-output conversion that goes through the agent's own model client.

NexusAI's default converter builds a fresh SDK client from the model *name* alone (`instructor.from_provider`), so the
api key, base URL and headers of the LLM object are dropped and the call goes to the vendor's own host with whatever the
process environment holds. That breaks every gateway or proxy and every per-workspace credential. This converter asks
the LLM object itself, which already carries its connection settings, and validates the JSON it returns.
"""

from __future__ import annotations

from typing import Any

from crewai.utilities.converter import Converter, ConverterError, handle_partial_json
from pydantic import BaseModel, ValidationError


class _DirectCallExtractor:
    """Quacks like nexusai's InternalInstructor: `to_pydantic()` returns a validated model."""

    def __init__(self, converter: "LlmCallConverter") -> None:
        self._converter = converter

    def to_pydantic(self) -> BaseModel:
        converter = self._converter
        response = converter.llm.call([
            {"role": "system", "content": converter.instructions},
            {"role": "user", "content": converter.text},
        ])
        try:
            return converter.model.model_validate_json(response)
        except ValidationError:
            partial: Any = handle_partial_json(result=response, model=converter.model, is_json_output=False, agent=None)
            if isinstance(partial, BaseModel):
                return partial
            if isinstance(partial, dict):
                return converter.model.model_validate(partial)
            raise ConverterError("The model's answer did not contain JSON matching the expected schema") from None


class LlmCallConverter(Converter):
    """Use as `Task(converter_cls=LlmCallConverter)`; retries and error wording are inherited from `Converter`."""

    def _create_instructor(self) -> Any:
        return _DirectCallExtractor(self)
