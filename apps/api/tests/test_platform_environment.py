"""Provider SDKs must reach the same gateway as litellm does."""

from __future__ import annotations

import pytest

from nexus_plugins.support.llm_service import configure_platform_model_keys


def test_gateway_address_is_exported_under_the_names_the_sdks_read(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_BASE", "OPENAI_BASE_URL", "ANTHROPIC_API_BASE", "ANTHROPIC_BASE_URL", "GROQ_BASE_URL", "GROQ_API_BASE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEXUS_OPENAI_API_BASE", "https://gateway.example/v1")
    monkeypatch.setenv("NEXUS_ANTHROPIC_API_BASE", "https://gateway.example")
    monkeypatch.setenv("NEXUS_GROQ_API_BASE", "https://groq.example/v1")
    configure_platform_model_keys()
    import os
    assert os.environ["OPENAI_API_BASE"] == os.environ["OPENAI_BASE_URL"] == "https://gateway.example/v1"
    assert os.environ["ANTHROPIC_API_BASE"] == os.environ["ANTHROPIC_BASE_URL"] == "https://gateway.example"
    assert "GROQ_BASE_URL" not in os.environ  # only SDKs that read *_BASE_URL get it


def test_an_address_set_by_the_operator_is_not_overwritten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_OPENAI_API_BASE", "https://gateway.example/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://operator.example/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    configure_platform_model_keys()
    import os
    assert os.environ["OPENAI_BASE_URL"] == "https://operator.example/v1"
