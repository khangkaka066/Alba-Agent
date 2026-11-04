# RAG engine

`MultiTenantRAGEngine` accepts a database engine, Qdrant client, and the metered model gateway embedding router. It reads PDF, DOCX, Markdown, and CSV, splits text with LlamaIndex `SentenceSplitter`, groups adjacent similar passages, and stores dense plus lexical sparse vectors in Qdrant. Retrieval fuses both indexes with reciprocal rank fusion.

Every retrieval applies a `tenant_id`, `workspace_id`, and `knowledge_base_id` filter to each Qdrant prefetch and the final query. The engine verifies the same scope on returned payloads. Database access uses the existing forced PostgreSQL RLS session. `TenantKnowledgeRetrievalTool` binds one scope for crew, NexusGen, or bot use; callers must construct that scope from authenticated claims.

Embedding models need an explicit price entry in `LiteLLMEmbeddingRouter`. Platform calls reserve tenant credit, record actual tokens and cost, then refund the unused reservation. BYOK credentials use the existing encrypted gateway store. The source is not installed in production images while the repository's exact license allowlist remains unresolved.
