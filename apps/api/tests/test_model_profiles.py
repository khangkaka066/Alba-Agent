"""Per-model connection settings."""

from __future__ import annotations

import pytest

from nexus_model_gateway.model_profiles import DEFAULT_PROFILE, ModelProfile, profile_for


def test_reasoning_models_wait_longer_and_small_models_fail_faster() -> None:
    assert profile_for("deepseek-reasoner").timeout_seconds > DEFAULT_PROFILE.timeout_seconds
    assert profile_for("openai/gpt-5-mini").timeout_seconds < DEFAULT_PROFILE.timeout_seconds


def test_unknown_model_uses_default_and_provider_prefix_is_ignored() -> None:
    assert profile_for("gpt-6-luna") == DEFAULT_PROFILE
    assert profile_for("openai/gpt-6-luna") == DEFAULT_PROFILE


def test_environment_override_wins_over_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_MODEL_PROFILES", '{"*mini*": {"timeout_seconds": 15, "max_retries": 0}}')
    assert profile_for("gpt-5-mini") == ModelProfile(timeout_seconds=15, max_retries=0)


def test_invalid_profile_is_rejected() -> None:
    with pytest.raises(ValueError):
        ModelProfile(timeout_seconds=0)
    with pytest.raises(ValueError):
        ModelProfile(max_retries=-1)
