"""Tenant-scoped MCP discovery over approved stdio and HTTPS SSE transports."""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlsplit

from autogen_ext.tools.mcp import McpWorkbench, SseServerParams, StdioServerParams
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from .hub import ToolBinding, UnifiedToolHub


@dataclass(frozen=True)
class McpConnection:
    label: str
    transport: Literal["stdio", "sse"]
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


class MCPConnector:
    def __init__(self, allowed_commands: frozenset[str], allowed_https_origins: frozenset[str]) -> None:
        self._allowed_commands = allowed_commands
        self._allowed_https_origins = allowed_https_origins

    def _validate(self, connection: McpConnection) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", connection.label):
            raise ValueError("MCP connection label is invalid")
        if connection.transport == "stdio":
            if connection.command not in self._allowed_commands or connection.url is not None:
                raise ValueError("MCP stdio command is not approved")
        else:
            parsed = urlsplit(connection.url or "")
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment or origin not in self._allowed_https_origins:
                raise ValueError("MCP SSE endpoint is not approved")

    @asynccontextmanager
    async def _session(self, connection: McpConnection) -> AsyncIterator[ClientSession]:
        self._validate(connection)
        if connection.transport == "stdio":
            assert connection.command is not None
            env = {
                **(connection.env or {}),
                "OTEL_SDK_DISABLED": "true",
                "CREWAI_DISABLE_TELEMETRY": "true",
            }
            parameters = StdioServerParameters(command=connection.command, args=list(connection.args), env=env)
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        else:
            assert connection.url is not None
            async with sse_client(connection.url, headers=connection.headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    async def discover(self, hub: UnifiedToolHub, connection: McpConnection) -> tuple[str, ...]:
        async with self._session(connection) as session:
            response = await session.list_tools()
        names: list[str] = []
        for native in response.tools:
            safe_name = re.sub(r"[^a-z0-9_]", "_", native.name.lower()).strip("_")[:50]
            if not safe_name:
                raise ValueError("MCP tool name cannot be normalized")
            name = f"nexus_mcp_{connection.label}_{safe_name}"

            async def invoke(arguments: dict[str, Any], *, _native_name: str = native.name) -> Any:
                async with self._session(connection) as live:
                    result = await live.call_tool(_native_name, arguments)
                if result.isError:
                    raise RuntimeError("Connected MCP tool reported an error")
                return [content.model_dump(mode="json") for content in result.content]

            hub.register(ToolBinding(
                name=name,
                description="Call an approved workspace tool",
                input_schema=dict(native.inputSchema),
                invoke=invoke,
            ))
            names.append(name)
        return tuple(names)

    def autogen_workbench(self, connection: McpConnection) -> McpWorkbench:
        self._validate(connection)
        if connection.transport == "stdio":
            assert connection.command is not None
            env = {
                **(connection.env or {}),
                "OTEL_SDK_DISABLED": "true",
                "CREWAI_DISABLE_TELEMETRY": "true",
            }
            return McpWorkbench(StdioServerParams(command=connection.command, args=list(connection.args), env=env))
        assert connection.url is not None
        return McpWorkbench(SseServerParams(url=connection.url, headers=connection.headers))
