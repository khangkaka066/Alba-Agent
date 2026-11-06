"""The architect must start from the model the user chose, not from the first name a provider happens to list.

A gateway can advertise a model that answers 404 when called. Sorted alphabetically, an upper-case name such as
`MiniMax-M2.5` comes first, so every fallback (the architect's own model, a team's default model, the consensus pair)
landed on it unless the user picked a model by hand."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.routers.architect import trusted_default_models
from architect.team_generator import ArchitectWorkspaceContext

LISTED = {"openai/MiniMax-M2.5", "openai/claude-3-5-haiku-20241022", "openai/gpt-6-luna", "openai/gpt-4.1-mini"}


def _credential(provider: str = "openai", default: bool = True, **defaults: str) -> SimpleNamespace:
    return SimpleNamespace(provider=provider, is_default=default, default_models=dict(defaults))


def _context(**kwargs: object) -> ArchitectWorkspaceContext:
    return ArchitectWorkspaceContext(tenant_id=uuid4(), workspace_id=uuid4(), **kwargs)  # type: ignore[arg-type]


def test_user_defaults_come_first_orchestrator_before_fast() -> None:
    trusted = trusted_default_models([_credential(fast="gpt-4.1-mini", orchestrator="gpt-6-luna")], LISTED)
    assert trusted == ("openai/gpt-6-luna", "openai/gpt-4.1-mini")


def test_default_provider_is_read_before_the_others() -> None:
    other = _credential("anthropic", default=False, orchestrator="claude-sonnet")
    mine = _credential(orchestrator="gpt-6-luna")
    assert trusted_default_models([other, mine], LISTED | {"anthropic/claude-sonnet"})[0] == "openai/gpt-6-luna"


def test_a_default_the_provider_no_longer_lists_is_dropped() -> None:
    assert trusted_default_models([_credential(orchestrator="retired-model")], LISTED) == ()


def test_fallback_is_the_trusted_model_not_the_alphabetical_first() -> None:
    context = _context(available_models=tuple(sorted(LISTED)), trusted_models=("openai/gpt-6-luna",))
    assert sorted(LISTED)[0] == "openai/MiniMax-M2.5"
    assert context.fallback_model == "openai/gpt-6-luna"


def test_without_defaults_the_old_behaviour_is_kept() -> None:
    context = _context(available_models=("openai/a", "openai/b"))
    assert context.fallback_model == "openai/a"
    assert context.consensus_pool == ("openai/a", "openai/b")
    assert _context().fallback_model == "openai/gpt-4.1-mini"


def test_consensus_pool_uses_trusted_models_only() -> None:
    context = _context(available_models=tuple(sorted(LISTED)), trusted_models=("openai/gpt-6-luna", "openai/gpt-4.1-mini"))
    assert context.consensus_pool[:2] == ("openai/gpt-6-luna", "openai/gpt-4.1-mini")
