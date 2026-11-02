"""Small real MCP stdio endpoint used by the protocol integration test."""

from __future__ import annotations

import asyncio

from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server


async def main() -> None:
    server: Server[object, object] = Server("nexus-test")

    @server.list_tools()  # type: ignore[misc, no-untyped-call]
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name="echo", description="Echo", inputSchema={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]})]

    @server.call_tool()  # type: ignore[misc]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[types.TextContent]:
        if name != "echo":
            raise ValueError("Unknown tool")
        return [types.TextContent(type="text", text=str(arguments["message"]))]

    async with stdio_server() as (read, write):
        await server.run(read, write, InitializationOptions(
            server_name="nexus-test", server_version="1.0.0",
            capabilities=server.get_capabilities(NotificationOptions(), {}),
        ))


if __name__ == "__main__":
    asyncio.run(main())
