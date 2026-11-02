"""Sandbox seam: a supervisor that picks an execution provider by name, and the providers that register with it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nexus_computer_sandbox import ComputerSandboxSupervisor, DockerSandboxProvider
from nexus_kernel import Context, Plugin
from nexus_plugins.seams import DATABASE, SANDBOX


class SandboxSupervisorPlugin(Plugin):
    """Creates, audits and drives isolated computers. It has no provider of its own: provider plugins add them."""

    name = "sandbox.supervisor"
    requires = (DATABASE,)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        ctx.provide(SANDBOX, ComputerSandboxSupervisor(ctx.service(DATABASE), None))


class DockerSandboxPlugin(Plugin):
    """Local Docker computers with dropped capabilities, no network and no new privileges."""

    name = "sandbox.docker"
    requires = (SANDBOX,)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        root = Path(str(config.get("root") or os.environ.get("NEXUS_COMPUTER_ROOT", "/tmp/nexus-computers")))
        image = str(config.get("image") or os.environ.get("NEXUS_SANDBOX_IMAGE", "python:3.11-slim"))
        ctx.on_dispose(ctx.service(SANDBOX).add_provider(DockerSandboxProvider(root, image=image)))
