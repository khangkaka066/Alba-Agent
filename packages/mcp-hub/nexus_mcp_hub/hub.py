"""One validated tool registry for crews, bot calls, and an internal MCP server."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from crewai.tools import BaseTool
from autogen_ext.tools.mcp import McpWorkbench, SseServerParams
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field, PrivateAttr, create_model

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]
TOOL_NAME = re.compile(r"^nexus_[a-z0-9_]{1,100}$")


@dataclass(frozen=True)
class ToolBinding:
    name: str
    description: str
    input_schema: dict[str, Any]
    invoke: ToolHandler


class WorkflowInvoker(Protocol):
    async def invoke_workflow(self, bot_id: UUID, workflow_id: UUID, task: str) -> Any: ...


def _assert_local_refs(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and (not isinstance(child, str) or not child.startswith("#/")):
                raise ValueError("Tool schemas may only contain local references")
            _assert_local_refs(child)
    elif isinstance(value, list):
        for child in value:
            _assert_local_refs(child)


def _type_for_property(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "string":
        return str
    if kind == "integer":
        return int
    if kind == "number":
        return float
    if kind == "boolean":
        return bool
    if kind == "array":
        return list[Any]
    if kind == "object":
        return dict[str, Any]
    return Any


def _args_model(binding: ToolBinding) -> type[BaseModel]:
    properties = binding.input_schema.get("properties", {})
    required = set(binding.input_schema.get("required", []))
    if not isinstance(properties, dict):
        raise ValueError("Tool input schema properties must be an object")
    fields: dict[str, Any] = {}
    for name, raw in properties.items():
        if not isinstance(raw, dict) or not name.isidentifier():
            raise ValueError("Tool input properties must be named objects")
        annotation = _type_for_property(raw)
        fields[name] = (annotation, Field(default=... if name in required else raw.get("default", None), description=str(raw.get("description", ""))))
    return create_model(f"NexusArgs_{binding.name}", **fields)


class CrewToolAdapter(BaseTool):
    name: str = "nexus_connected_tool"
    description: str = "Invoke a scoped connected tool"
    args_schema: type[BaseModel] = BaseModel

    _binding: ToolBinding = PrivateAttr()

    def __init__(self, binding: ToolBinding) -> None:
        super().__init__(name=binding.name, description=binding.description, args_schema=_args_model(binding))
        self._binding = binding

    async def _arun(self, **kwargs: Any) -> str:
        Draft202012Validator(self._binding.input_schema).validate(kwargs)
        result = await self._binding.invoke(kwargs)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    def _run(self, **kwargs: Any) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._arun(**kwargs))
        raise RuntimeError("Use the async connected tool inside a running event loop")


class UnifiedToolHub:
    def __init__(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID | None = None) -> None:
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.bot_id = bot_id
        self._bindings: dict[str, ToolBinding] = {}

    def register(self, binding: ToolBinding) -> None:
        if not TOOL_NAME.fullmatch(binding.name) or not binding.description.strip():
            raise ValueError("Connected tool name or description is invalid")
        if binding.name in self._bindings:
            raise ValueError("Connected tool name is already registered")
        if len(json.dumps(binding.input_schema)) > 262_144 or binding.input_schema.get("type") != "object":
            raise ValueError("Connected tool requires a bounded object input schema")
        _assert_local_refs(binding.input_schema)
        Draft202012Validator.check_schema(binding.input_schema)
        self._bindings[binding.name] = binding

    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            binding = self._bindings[name]
        except KeyError as error:
            raise LookupError("Connected tool is not published in this workspace") from error
        Draft202012Validator(binding.input_schema).validate(arguments)
        return await binding.invoke(arguments)

    async def call_for_bot(self, bot_id: UUID, name: str, arguments: dict[str, Any]) -> Any:
        if self.bot_id is None or self.bot_id != bot_id:
            raise PermissionError("Tool hub does not belong to this bot")
        return await self.call(name, arguments)

    def crew_tools(self) -> tuple[CrewToolAdapter, ...]:
        return tuple(CrewToolAdapter(self._bindings[name]) for name in self.tool_names())

    def nexusgen_workbench(self, sse_url: str, access_token: str) -> McpWorkbench:
        if not sse_url.startswith("https://") or not sse_url.endswith("/sse"):
            raise ValueError("Internal MCP workbench requires an HTTPS SSE endpoint")
        if len(access_token) < 32:
            raise ValueError("Internal MCP access token must be at least 32 characters")
        return McpWorkbench(SseServerParams(url=sse_url, headers={"X-Nexus-Tool-Token": access_token}))

    def publish_workflow(
        self,
        workflow_id: UUID,
        runner: WorkflowInvoker,
    ) -> str:
        if self.bot_id is None:
            raise ValueError("Workflow publication requires a bot-scoped hub")
        bot_id = self.bot_id
        name = f"nexus_workflow_{workflow_id.hex}"

        async def invoke(arguments: dict[str, Any]) -> dict[str, Any]:
            state = await runner.invoke_workflow(bot_id, workflow_id, str(arguments["task"]))
            return {"run_id": str(state.run_id), "status": state.status, "outputs": state.node_outputs}

        self.register(ToolBinding(
            name=name,
            description="Run a published workspace workflow",
            input_schema={"type": "object", "properties": {"task": {"type": "string", "minLength": 1}}, "required": ["task"], "additionalProperties": False},
            invoke=invoke,
        ))
        return name

    def mcp_server(self) -> Server[Any, Any]:
        server: Server[Any, Any] = Server("nexus-hub")

        @server.list_tools()  # type: ignore[misc, no-untyped-call]
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(name=binding.name, description=binding.description, inputSchema=binding.input_schema)
                for binding in (self._bindings[name] for name in self.tool_names())
            ]

        @server.call_tool()  # type: ignore[misc]
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
            result = await self.call(name, arguments)
            content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            return [types.TextContent(type="text", text=content)]

        return server

    @staticmethod
    def _initialization(server: Server[Any, Any]) -> InitializationOptions:
        return InitializationOptions(
            server_name="nexus-hub", server_version="1.0.0",
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(), experimental_capabilities={},
            ),
        )

    async def serve_stdio(self) -> None:
        server = self.mcp_server()
        async with stdio_server() as (read, write):
            await server.run(read, write, self._initialization(server))

    def sse_app(self, access_token: str) -> Callable[..., Awaitable[None]]:
        if len(access_token) < 32:
            raise ValueError("Internal MCP access token must be at least 32 characters")
        server = self.mcp_server()
        transport = SseServerTransport("/messages/")

        async def app(scope: dict[str, Any], receive: Callable[..., Awaitable[Any]], send: Callable[..., Awaitable[None]]) -> None:
            if scope.get("type") != "http":
                raise ValueError("Internal MCP server only accepts HTTP")
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            provided = headers.get(b"x-nexus-tool-token", b"").decode("utf-8", errors="replace")
            if not hmac.compare_digest(provided, access_token):
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
            path = scope.get("path")
            if path == "/sse" and scope.get("method") == "GET":
                async with transport.connect_sse(scope, receive, send) as (read, write):
                    await server.run(read, write, self._initialization(server))
            elif path == "/messages/" and scope.get("method") == "POST":
                await transport.handle_post_message(scope, receive, send)
            else:
                await send({"type": "http.response.start", "status": 404, "headers": []})
                await send({"type": "http.response.body", "body": b"Not found"})

        return app
