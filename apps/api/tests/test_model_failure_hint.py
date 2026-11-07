"""A run that fails because a model does not exist must say which models the user can switch to (opencode shows
`ProviderModelNotFoundError` with suggestions) instead of a bare provider message."""

from __future__ import annotations

import pytest

from checkpoints.failure import describe_failure, is_model_not_found, with_model_suggestions


class NotFoundError(Exception):
    pass


@pytest.mark.parametrize("error", [
    NotFoundError("The requested resource or model was not found. (request id: 2026)"),
    RuntimeError("litellm.NotFoundError: model_not_found: The model `MiniMax-M2.5` does not exist"),
    ValueError("Unknown model: kimi-k3"),
    RuntimeError("404 No such model gpt-9"),
])
def test_provider_messages_about_a_missing_model_are_recognised(error: Exception) -> None:
    assert is_model_not_found(error)


@pytest.mark.parametrize("error", [
    RuntimeError("File not found: todo.py"),
    NotFoundError("Run not found"),
    RuntimeError("model overloaded, retry later"),
    KeyError("Architect_crew_1_3Output"),
])
def test_other_errors_are_not_taken_for_a_missing_model(error: Exception) -> None:
    assert not is_model_not_found(error)


def test_suggestions_are_added_to_the_stored_failure() -> None:
    failure = describe_failure(NotFoundError("The requested resource or model was not found."))
    shown = with_model_suggestions(failure, ("openai/gpt-6-luna", "openai/gpt-4.1-mini"))
    assert shown["suggested_models"] == ["openai/gpt-6-luna", "openai/gpt-4.1-mini"]
    assert "openai/gpt-6-luna" in shown["error_message"] and shown["error_message"].startswith("The requested resource")
    assert failure["error_message"] == "The requested resource or model was not found.", "the input is not changed"


def test_without_suggestions_the_failure_is_unchanged() -> None:
    failure = describe_failure(NotFoundError("model not found"))
    assert with_model_suggestions(failure, ()) == failure
