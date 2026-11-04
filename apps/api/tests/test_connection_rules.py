"""Where a model call goes must not depend on which vendor or gateway the key came from."""

from __future__ import annotations

from dataclasses import dataclass

from nexus_model_gateway.connection import effective_api_base

PLATFORM = {"NEXUS_OPENAI_API_BASE": "https://platform-gateway.example/v1", "NEXUS_OLLAMA_API_BASE": "http://ollama:11434"}


@dataclass
class Credential:
    api_base: str | None = None


def test_the_platform_key_uses_the_platform_gateway() -> None:
    assert effective_api_base("openai", None, None, PLATFORM) == "https://platform-gateway.example/v1"


def test_a_workspace_key_never_borrows_the_platform_gateway() -> None:
    assert effective_api_base("openai", None, Credential(), PLATFORM) is None


def test_a_workspace_gateway_wins_over_the_platform_one() -> None:
    assert effective_api_base("openai", None, Credential("https://their-proxy.example/v1"), PLATFORM) == "https://their-proxy.example/v1"


def test_an_explicit_request_address_wins_over_everything() -> None:
    assert effective_api_base("openai", "https://explicit.example", Credential("https://their-proxy.example"), PLATFORM) == "https://explicit.example"


def test_local_providers_keep_the_platform_fallback() -> None:
    assert effective_api_base("ollama", None, Credential(), PLATFORM) == "http://ollama:11434"


def test_nothing_configured_means_the_vendor_default() -> None:
    assert effective_api_base("anthropic", None, None, {}) is None
