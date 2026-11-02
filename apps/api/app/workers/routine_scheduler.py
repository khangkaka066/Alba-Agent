"""Periodic workspace-scoped routine dispatch."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import UUID

from bots.runner import BotRunner

ScopeSource = Callable[[], Awaitable[tuple[tuple[UUID, UUID], ...]]]
RunnerFactory = Callable[[UUID, UUID], BotRunner]


class RoutineScheduler:
    def __init__(self, scopes: ScopeSource, runner_factory: RunnerFactory, poll_seconds: float = 30) -> None:
        if poll_seconds <= 0:
            raise ValueError("Scheduler poll interval must be positive")
        self._scopes = scopes
        self._runner_factory = runner_factory
        self._poll_seconds = poll_seconds

    async def run_once(self, when: datetime | None = None) -> dict[tuple[UUID, UUID], tuple[UUID, ...]]:
        instant = when or datetime.now(timezone.utc)
        results: dict[tuple[UUID, UUID], tuple[UUID, ...]] = {}
        for tenant_id, workspace_id in await self._scopes():
            results[(tenant_id, workspace_id)] = await self._runner_factory(tenant_id, workspace_id).run_due(instant)
        return results

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except asyncio.TimeoutError:
                continue
