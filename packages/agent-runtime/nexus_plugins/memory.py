"""Run state: append-only checkpoints that back pause, resume and time-travel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from checkpoints.store import CheckpointStore
from nexus_kernel import Context, Plugin
from nexus_plugins.seams import CHECKPOINTS, DATABASE, REDIS


class CheckpointsPlugin(Plugin):
    name = "memory.checkpoints"
    requires = (DATABASE, REDIS)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        ctx.provide(CHECKPOINTS, CheckpointStore(ctx.service(DATABASE), ctx.service(REDIS)))
