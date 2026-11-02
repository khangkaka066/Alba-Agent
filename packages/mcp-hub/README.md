# MCP hub

`UnifiedToolHub` is a workspace or bot-scoped registry. `MCPConnector` discovers tools from approved stdio commands or allowlisted HTTPS SSE origins. `OpenAPIImporter` accepts bounded OpenAPI 3.1 JSON with local references and allowlisted HTTPS origins. Imported write operations require an injected approval guard; redirects are disabled.

The registry validates JSON Schema arguments before invocation and converts its bindings to Crew tools. It can publish workflows through a bot runner and serve the same bindings as an authenticated internal MCP server over stdio or SSE. `autogen_workbench()` connects AutoGen to that internal HTTPS endpoint with an access token. A connector can also construct a direct AutoGen workbench for an administrator-approved external MCP server.

Configure allowed commands, origins, headers, and the internal access token only on the trusted server side. Start the internal SSE ASGI app at `/sse` and `/messages/`. Tool names, credentials, and publication scope are not taken from model-generated arguments.
