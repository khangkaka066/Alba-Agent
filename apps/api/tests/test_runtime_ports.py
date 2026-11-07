"""The desktop app runs Postgres and Redis on private ports; the defaults used by docker-compose must not change."""

from __future__ import annotations

from typing import Any

import pytest

from app.models.connection import create_runtime_engine
from app.workers.jobs import _redis_url


def _runtime_env(monkeypatch: pytest.MonkeyPatch, **extra: str) -> None:
    for key, value in {"NEXUS_DB_USER": "nexus_runtime", "NEXUS_DB_PASSWORD": "p", "NEXUS_DB_HOST": "db", "NEXUS_DB_NAME": "nexus", **extra}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("NEXUS_REDIS_URL", raising=False)


def test_database_port_defaults_to_5432_and_can_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _runtime_env(monkeypatch)
    monkeypatch.delenv("NEXUS_DB_PORT", raising=False)
    assert create_runtime_engine().url.port == 5432
    monkeypatch.setenv("NEXUS_DB_PORT", "55432")
    assert create_runtime_engine().url.port == 55432


def test_redis_port_defaults_to_6379_and_can_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _runtime_env(monkeypatch, NEXUS_REDIS_HOST="cache", NEXUS_REDIS_PASSWORD="pw")
    monkeypatch.delenv("NEXUS_REDIS_PORT", raising=False)
    assert _redis_url().endswith("@cache:6379/0")
    monkeypatch.setenv("NEXUS_REDIS_PORT", "56379")
    assert _redis_url().endswith("@cache:56379/0")


def test_redis_client_uses_the_port_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from nexus_kernel import Context
    from nexus_plugins.infrastructure import InfrastructurePlugin
    from nexus_plugins.seams import REDIS

    _runtime_env(monkeypatch, NEXUS_REDIS_PASSWORD="pw", NEXUS_REDIS_PORT="56379", NEXUS_QDRANT_URL="http://127.0.0.1:1")
    captured: dict[str, Any] = {}

    async def check() -> None:
        ctx = Context()
        await InfrastructurePlugin().apply(ctx, {})
        captured["port"] = ctx.service(REDIS).connection_pool.connection_kwargs["port"]

    asyncio.run(check())
    assert captured["port"] == 56379
