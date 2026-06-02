# RAG (Retrieval-Augmented Generation)

## Purpose
建筑规范知识检索 — ChromaDB 向量库存储 GB/T 50344 等标准条文，语义检索辅助 LLM 生成合规报告。

## Requirements

### Requirement: Document Ingestion
System SHALL support Word (.docx) and PDF (.pdf) document ingestion into ChromaDB.

#### Scenario: Build vector store
- **WHEN** `python scripts/build_rag.py` is run with a docx file in `rag_data/`
- **THEN** system SHALL parse the document, split into chunks (500 chars, 100 overlap), embed with text-embedding-v3, and store in `chroma_db/`

### Requirement: Semantic Search
System SHALL expose `search_regulations(query, k=5)` for free-text ChromaDB similarity search.

#### Scenario: Search building standard
- **WHEN** `search_regulations("裂缝宽度标准", k=5)` is called
- **THEN** system SHALL return top-5 relevant document chunks from ChromaDB

#### Scenario: Vector store unavailable
- **WHEN** ChromaDB is not initialized
- **THEN** `search_regulations` SHALL return empty string (not crash)

### Requirement: Knowledge Search Tool
The `search_knowledge` tool SHALL prioritize ChromaDB regulation search, falling back to SQLite user memory search.

#### Scenario: ChromaDB available
- **WHEN** LLM calls `search_knowledge(query="面砖脱落处理")`
- **THEN** tool SHALL return matching building standards from ChromaDB

#### Scenario: ChromaDB unavailable
- **WHEN** ChromaDB fails or returns empty
- **THEN** tool SHALL fall back to `search_memories_by_keyword` from SQLite

### Requirement: Embedding API
Embedding SHALL use DashScope native API (not compatible mode) with `text-embedding-v3` model, batch size max 10.

#### Scenario: Batch embedding
- **WHEN** embedding 100 text chunks
- **THEN** system SHALL send requests in batches of 10

### Requirement: Separate Storage
ChromaDB vector data SHALL live in `chroma_db/` (gitignored), separate from the main SQLAlchemy `inspection.db`. Knowledge metadata SHALL be stored in `knowledge_documents` and `knowledge_chunks` SQL tables.
