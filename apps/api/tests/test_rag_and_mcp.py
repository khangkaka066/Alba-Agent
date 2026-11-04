"""Real Qdrant isolation and connected-tool conversion tests."""

from __future__ import annotations

import sys
import asyncio
import io
import json
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from docx import Document
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.gateway_store import SqlGatewayStore
from nexus_mcp_hub import MCPConnector, McpConnection, OpenAPIImporter, ToolBinding, UnifiedToolHub
from nexus_model_gateway import CredentialCipher, LiteLLMEmbeddingRouter, ModelRate
from nexus_rag_engine import KnowledgeScope, MultiTenantRAGEngine, TenantKnowledgeRetrievalTool
from nexus_rag_engine.engine import _parse_document


@asynccontextmanager
async def connect_mcp_server(server: Any) -> Any:
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        server_task = asyncio.create_task(
            server.run(*server_streams, server.create_initialization_options())
        )
        try:
            async with ClientSession(*client_streams) as session:
                await session.initialize()
                yield session
        finally:
            server_task.cancel()
            await asyncio.gather(server_task, return_exceptions=True)


def test_supported_document_parsers() -> None:
    assert "alpha" in _parse_document("guide.md", b"# alpha\nBeta")
    assert "alpha" in _parse_document("rows.csv", b"name,value\nalpha,1\n")
    document = Document()
    document.add_paragraph("alpha document")
    stream = io.BytesIO()
    document.save(stream)
    assert "alpha document" in _parse_document("guide.docx", stream.getvalue())
    # A minimal, valid PDF with one visible text stream.
    content = b"BT /F1 12 Tf 72 720 Td (alpha pdf) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    assert "alpha pdf" in _parse_document("guide.pdf", bytes(pdf))


def test_real_qdrant_isolation_and_metered_embeddings() -> None:
    if "NEXUS_TEST_DATABASE_URL" not in os.environ or "NEXUS_TEST_QDRANT_URL" not in os.environ:
        pytest.skip("Integration services are not configured")

    async def check() -> None:
        tenant_a, tenant_b = uuid4(), uuid4()
        workspace_a, workspace_b = uuid4(), uuid4()
        base_a, base_b = uuid4(), uuid4()
        db_url = os.environ["NEXUS_TEST_DATABASE_URL"]
        admin = create_async_engine(db_url)
        async with admin.begin() as connection:
            await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:a, 'RAG A'), (:b, 'RAG B')"), {"a": tenant_a, "b": tenant_b})
            await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:wa, :a, 'A'), (:wb, :b, 'B')"), {"wa": workspace_a, "wb": workspace_b, "a": tenant_a, "b": tenant_b})
            await connection.execute(text("INSERT INTO knowledge_bases (id, tenant_id, workspace_id, name, embedding_model) VALUES (:ka, :a, :wa, 'A', 'openai/test-embed'), (:kb, :b, :wb, 'B', 'openai/test-embed')"), {"ka": base_a, "kb": base_b, "a": tenant_a, "b": tenant_b, "wa": workspace_a, "wb": workspace_b})
            await connection.execute(text("INSERT INTO tenant_budgets (tenant_id, remaining_usd, reserved_usd) VALUES (:a, 1, 0), (:b, 1, 0)"), {"a": tenant_a, "b": tenant_b})
        runtime_url = os.environ.get("NEXUS_TEST_APP_DATABASE_URL", db_url)
        db = create_async_engine(runtime_url)
        qdrant = AsyncQdrantClient(url=os.environ["NEXUS_TEST_QDRANT_URL"])

        async def fake_embedding(**kwargs: object) -> dict[str, object]:
            values = kwargs["input"]
            assert isinstance(values, list)
            return {"data": [{"embedding": [1.0, 0.0, 0.5]} for _ in values], "usage": {"prompt_tokens": len(values) * 3}}

        embeddings = LiteLLMEmbeddingRouter(
            SqlGatewayStore(db, CredentialCipher(b"x" * 32)),
            {("openai", "test-embed"): ModelRate(Decimal("0.50"), Decimal("0"))},
            embedding=fake_embedding,
            token_counter=lambda model, values: len(values) * 3,
        )
        rag = MultiTenantRAGEngine(db, qdrant, embeddings)
        scope_a = KnowledgeScope(tenant_a, workspace_a, base_a)
        scope_b = KnowledgeScope(tenant_b, workspace_b, base_b)
        try:
            await rag.ingest(scope_a, "a.md", b"# Shared phrase\nOnly tenant A secret kiwi orchard.")
            await rag.ingest(scope_b, "b.md", b"# Shared phrase\nOnly tenant B secret cobalt harbor.")
            original_query = qdrant.query_points

            async def checked_query(*args: Any, **kwargs: Any) -> Any:
                query_filter = kwargs["query_filter"]
                prefetch = kwargs["prefetch"]
                assert isinstance(prefetch, list) and len(prefetch) == 2
                assert all(item.filter == query_filter for item in prefetch)
                assert len(query_filter.must) == 3
                return await original_query(*args, **kwargs)

            setattr(qdrant, "query_points", checked_query)
            hits_a = await rag.retrieve(scope_a, "Shared phrase")
            hits_b = await rag.retrieve(scope_b, "Shared phrase")
            assert hits_a and hits_b
            assert all("tenant A" in hit.text and "tenant B" not in hit.text for hit in hits_a)
            assert all("tenant B" in hit.text and "tenant A" not in hit.text for hit in hits_b)
            with pytest.raises(LookupError):
                await rag.retrieve(KnowledgeScope(tenant_a, workspace_a, base_b), "Shared phrase")
            tool = TenantKnowledgeRetrievalTool(rag, scope_a)
            assert "tenant A" in await tool._arun("Shared phrase")
            assert tool.for_nexusgen().name == "nexus_knowledge_retrieve"
            async with admin.connect() as connection:
                rows = await connection.execute(text("SELECT tenant_id, count(*) FROM token_usage_logs WHERE tenant_id IN (:a, :b) GROUP BY tenant_id"), {"a": tenant_a, "b": tenant_b})
                assert {row[0] for row in rows} == {tenant_a, tenant_b}
        finally:
            await qdrant.close()
            await db.dispose()
            await admin.dispose()

    asyncio.run(check())


def test_tool_hub_openapi_and_workflow_conversion() -> None:
    async def check() -> None:
        tenant, workspace, bot, workflow = uuid4(), uuid4(), uuid4(), uuid4()
        hub = UnifiedToolHub(tenant, workspace, bot)

        async def echo(arguments: dict[str, object]) -> dict[str, object]:
            return {"echo": arguments["message"]}

        hub.register(ToolBinding("nexus_echo", "Echo a message", {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"], "additionalProperties": False}, echo))
        assert json.loads(await hub.crew_tools()[0]._arun(message="hi")) == {"echo": "hi"}
        with pytest.raises(PermissionError):
            await hub.call_for_bot(uuid4(), "nexus_echo", {"message": "hi"})

        class Runner:
            async def invoke_workflow(self, bot_id: UUID, workflow_id: UUID, task: str) -> SimpleNamespace:
                assert bot_id == bot and workflow_id == workflow
                return SimpleNamespace(run_id=uuid4(), status="completed", node_outputs={"result": task})

        workflow_name = hub.publish_workflow(workflow, Runner())
        assert (await hub.call_for_bot(bot, workflow_name, {"task": "analyze"}))["outputs"] == {"result": "analyze"}
        async with connect_mcp_server(hub.mcp_server()) as session:
            published = await session.list_tools()
            assert workflow_name in {tool.name for tool in published.tools}
            result = await session.call_tool(workflow_name, {"task": "via protocol"})
            assert "via protocol" in str(result.content)
        assert callable(hub.sse_app("x" * 32))
        assert hub.nexusgen_workbench("https://nexus.example.test/sse", "x" * 32) is not None
        with pytest.raises(ValueError):
            hub.sse_app("short")

        async def transport(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "api.example.test"
            return httpx.Response(200, json={"item": request.url.path.rsplit("/", 1)[-1]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            importer = OpenAPIImporter(hub, frozenset({"https://api.example.test"}), client)
            names = importer.import_spec({
                "openapi": "3.1.0", "servers": [{"url": "https://api.example.test"}],
                "paths": {"/items/{item_id}": {"get": {"operationId": "getItem", "parameters": [{"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}}]}}},
            })
            assert await hub.call(names[0], {"path": {"item_id": "a b"}}) == {"item": "a b"}
            with pytest.raises(ValueError):
                importer.import_spec({"openapi": "3.1.0", "servers": [{"url": "https://evil.test"}], "paths": {}})

    asyncio.run(check())


def test_real_stdio_mcp_discovery_and_nexusgen_workbench() -> None:
    async def check() -> None:
        fixture = Path(__file__).with_name("fixtures") / "mcp_echo_server.py"
        connector = MCPConnector(frozenset({sys.executable}), frozenset())
        connection = McpConnection("fixture", "stdio", command=sys.executable, args=(str(fixture),))
        hub = UnifiedToolHub(uuid4(), uuid4())
        names = await connector.discover(hub, connection)
        assert names == ("nexus_mcp_fixture_echo",)
        assert "hello" in await hub.crew_tools()[0]._arun(message="hello")
        workbench = connector.nexusgen_workbench(connection)
        await workbench.start()
        try:
            tools = await workbench.list_tools()
            assert any(tool["name"] == "echo" for tool in tools)
            result = await workbench.call_tool("echo", {"message": "agent"})
            assert "agent" in str(result)
        finally:
            await workbench.stop()

    asyncio.run(check())
