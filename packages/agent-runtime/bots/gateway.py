"""Budgeted model gateway adapter for persistent bot conversations."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, cast

from nexus_core_schema.models import PersistentBotSpec
from nexus_model_gateway.router import GatewayRequest, LiteLLMRouter, Provider


class GatewayBotResponder:
    def __init__(self, gateway: LiteLLMRouter, max_input_tokens: int = 4096, max_output_tokens: int = 1024,
                 tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
                 available_workflows: dict[str, str] | None = None) -> None:
        if max_input_tokens < 1 or max_output_tokens < 1:
            raise ValueError("Bot token limits must be positive")
        self._gateway = gateway
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._tool_executor = tool_executor
        self._available_workflows = available_workflows or {}

    async def __call__(self, bot: PersistentBotSpec, messages: tuple[tuple[str, str], ...]) -> str:
        provider_name, separator, model = bot.model.partition("/")
        if not separator or not model or provider_name not in (
            "openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "groq", "mistral", "together_ai"
        ):
            raise ValueError("Bot model must use an approved provider/model name")
        transcript = tuple({"role": role, "content": content} for role, content in messages)
        if self._tool_executor is None or not bot.tool_ids:
            return (await self._gateway.complete(GatewayRequest(
                tenant_id=bot.tenant_id, workspace_id=bot.workspace_id,
                provider=cast(Provider, provider_name), model=model, messages=transcript,
                max_input_tokens=self._max_input_tokens, max_output_tokens=self._max_output_tokens,
                billing_mode=bot.billing_mode, agent_name=f"bot:{bot.id}",
                credential_id=bot.credential_id, api_base=bot.api_base,
            ))).content
        system = {"role": "system", "content": (
            "You are an action-capable teammate. Return exactly one JSON object per turn: "
            '{"action":"tool","tool_id":"assigned ID","arguments":{...}} or '
            '{"action":"final","reply":"honest answer"}. Use assigned tools when the user asks you to execute. '
            "Never claim an artifact or action exists until its tool returned success. "
            f"Assigned tools: {json.dumps(list(bot.tool_ids))}. "
            f"Existing workflows (name to ID): {json.dumps(self._available_workflows)}. "
            "peer_workflow requires arguments {workflow_id, inputs}. Media requires {kind, prompt, model, filename}. "
            "Stop after at most four tool calls."
        )}
        history = [system, *transcript]
        evidence: list[dict[str, Any]] = []
        for _attempt in range(5):
            response = await self._gateway.complete(GatewayRequest(
                tenant_id=bot.tenant_id, workspace_id=bot.workspace_id,
                provider=cast(Provider, provider_name), model=model, messages=tuple(history),
                max_input_tokens=self._max_input_tokens, max_output_tokens=self._max_output_tokens,
                billing_mode=bot.billing_mode, agent_name=f"bot:{bot.id}",
                credential_id=bot.credential_id, api_base=bot.api_base,
            ))
            raw = response.content.strip()
            try:
                decision = json.loads(raw.removeprefix("```json").removesuffix("```").strip())
            except json.JSONDecodeError:
                return raw + ("\n\nCompleted tool results: " + json.dumps(evidence) if evidence else "")
            if not isinstance(decision, dict):
                raise ValueError("Bot action response must be a JSON object")
            if decision.get("action") == "final":
                reply = str(decision.get("reply", "")).strip()
                if not reply:
                    raise ValueError("Bot final answer is empty")
                return reply + ("\n\nCompleted tool results: " + json.dumps(evidence) if evidence else "")
            tool_id = str(decision.get("tool_id", ""))
            arguments = decision.get("arguments")
            if decision.get("action") != "tool" or tool_id not in bot.tool_ids or not isinstance(arguments, dict):
                raise ValueError("Bot requested an unassigned or malformed tool action")
            result = await self._tool_executor(tool_id, arguments)
            evidence.append({"tool_id": tool_id, "result": result})
            history.extend(({"role": "assistant", "content": raw}, {"role": "user", "content": "Tool result: " + json.dumps(result, default=str)[:12000]}))
        return "Tool call limit reached. Completed tool results: " + json.dumps(evidence)
