"""Multi-turn code execution: AutoGen coder and reviewer agents working inside a sandbox computer."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from agent_skills import SkillSpec
from app.billing.plans import enforce_monthly_sandbox_quota
from app.models import AgentSkill
from app.models.scope import scoped_session
from autogen_bridge.sandbox_team import AutoGenSandboxRunner
from nexus_kernel import Context, Plugin
from nexus_plugins.seams import DATABASE, LLM, SANDBOX, SANDBOX_RUNNER, TOOLS


class SandboxRunnerPlugin(Plugin):
    name = "sandbox.runner"
    requires = (DATABASE, LLM, SANDBOX, TOOLS)

    async def apply(self, ctx: Context, config: Mapping[str, Any]) -> None:
        engine, llm, tools = ctx.service(DATABASE), ctx.service(LLM), ctx.service(TOOLS)

        async def guard_quota(tenant_id: UUID, workspace_id: UUID, maximum_seconds: int) -> None:
            await enforce_monthly_sandbox_quota(engine, tenant_id, workspace_id, Decimal(maximum_seconds))

        async def skill_instructions(tenant_id: UUID, workspace_id: UUID, slugs: tuple[str, ...]) -> dict[str, str]:
            if not slugs:
                return {}
            async with scoped_session(engine, tenant_id, workspace_id) as session:
                rows = (await session.scalars(select(AgentSkill).where(AgentSkill.slug.in_(slugs)))).all()
            return {row.slug: SkillSpec.from_markdown(row.content).body for row in rows}

        async def resolve_tools(tenant_id: UUID, workspace_id: UUID, run_id: UUID, tool_ids: tuple[str, ...]) -> list[Any]:
            return tools.autogen_tools(tenant_id, workspace_id, run_id, tool_ids)

        runner = AutoGenSandboxRunner(ctx.service(SANDBOX), llm.autogen_client, guard_quota)
        runner.set_skill_resolver(skill_instructions)
        runner.set_tool_resolver(resolve_tools)
        ctx.provide(SANDBOX_RUNNER, runner)
