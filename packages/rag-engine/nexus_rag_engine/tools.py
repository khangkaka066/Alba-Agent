"""One scoped retrieval capability shared across agent engines and bots."""

from __future__ import annotations

import asyncio
import json

from autogen_core.tools import FunctionTool
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from .engine import EmbeddingAccess, KnowledgeScope, MultiTenantRAGEngine


class KnowledgeQuery(BaseModel):
    query: str = Field(min_length=1, description="Question to answer from this knowledge base")


class TenantKnowledgeRetrievalTool(BaseTool):
    name: str = "nexus_knowledge_retrieve"
    description: str = "Retrieve scoped knowledge passages with dense and lexical search"
    args_schema: type[BaseModel] = KnowledgeQuery

    _engine: MultiTenantRAGEngine = PrivateAttr()
    _scope: KnowledgeScope = PrivateAttr()
    _access: EmbeddingAccess = PrivateAttr()

    def __init__(self, engine: MultiTenantRAGEngine, scope: KnowledgeScope, access: EmbeddingAccess = EmbeddingAccess()) -> None:
        super().__init__(name="nexus_knowledge_retrieve", description="Retrieve scoped knowledge passages with dense and lexical search")
        self._engine = engine
        self._scope = scope
        self._access = access

    async def retrieve(self, query: str) -> str:
        hits = await self._engine.retrieve(self._scope, query, self._access)
        return json.dumps([
            {"document_id": str(hit.document_id), "filename": hit.filename, "text": hit.text,
             "score": hit.score, "chunk_index": hit.chunk_index}
            for hit in hits
        ], ensure_ascii=False)

    async def _arun(self, query: str) -> str:
        return await self.retrieve(query)

    def _run(self, query: str) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.retrieve(query))
        raise RuntimeError("Use the async retrieval method inside a running event loop")

    def for_autogen(self) -> FunctionTool:
        return FunctionTool(self.retrieve, name=self.name, description=self.description)
