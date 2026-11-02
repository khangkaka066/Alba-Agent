"""Model access: credentials, routers and provider clients behind one service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nexus_kernel import Context, Plugin
from nexus_plugins.seams import DATABASE, LLM
from nexus_plugins.support.llm_service import LlmService, configure_platform_model_keys, load_model_rates


class GatewayLlmPlugin(Plugin):
    name = "llm.gateway"
    requires = (DATABASE,)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        configure_platform_model_keys()
        ctx.provide(LLM, LlmService(ctx.service(DATABASE), load_model_rates()))
