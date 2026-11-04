"""Which address a model call goes to. One rule for completions and embeddings, whatever the provider is."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol

_LOCAL_PROVIDERS = ("ollama", "vllm")


class _HasApiBase(Protocol):
    @property
    def api_base(self) -> str | None: ...


def effective_api_base(
    provider: str,
    request_base: str | None,
    credential: _HasApiBase | None,
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """The request's own address, else the workspace credential's, else the platform's.

    The platform address (`NEXUS_<PROVIDER>_API_BASE`) belongs to the platform's own key. When a workspace brings its own
    credential without an address, the call goes to the vendor's default host; falling back to the platform gateway would
    send that workspace's key to the wrong party. Local providers hold no secret and keep the platform fallback.
    """
    if request_base:
        return request_base
    if credential is not None and credential.api_base:
        return credential.api_base
    if credential is not None and provider not in _LOCAL_PROVIDERS:
        return None
    return (environment if environment is not None else os.environ).get(f"NEXUS_{provider.upper()}_API_BASE") or None
