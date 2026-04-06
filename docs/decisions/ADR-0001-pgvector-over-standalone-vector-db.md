# ADR-0001: PostgreSQL with pgvector over Standalone Vector Databases

## Status
Accepted

## Context
DocsQA requires storing document chunks, metadata (hierarchical headings, file paths, character offsets, content hashes), relational ingestion job logs, and high-dimensional vector embeddings (typically 384 to 1536 dimensions). In addition, hybrid retrieval requires full-text search capability over the exact same text chunks.

We evaluated whether to use a dedicated vector database (Pinecone, Qdrant, Milvus) versus PostgreSQL with the `pgvector` extension.

## Decision Drivers
- **Data consistency & dual-write problem:** Having document metadata in Postgres and vectors in a separate database leads to distributed transaction complexity, sync lag, and orphan records.
- **Hybrid search under one roof:** Postgres natively supports both `tsvector` full-text search and vector similarity indexes (HNSW and IVFFlat), allowing unified SQL queries.
- **Operational overhead:** Maintaining a single database container in Docker Compose reduces memory footprint, backup complexity, and local development burden.
- **Scale:** DocsQA handles tens of thousands of chunks, well within PostgreSQL's sweet spot where pgvector HNSW provides sub-millisecond query latencies.

## Considered Options
1. **PostgreSQL with pgvector (Selected):**
   - *Pros:* ACID compliance, relational joins, unified backups, native `to_tsvector` for full-text search, HNSW indexing for rapid cosine/inner product search, zero network hops between text and vector data.
   - *Cons:* Slightly higher memory consumption for HNSW indexes compared to specialized in-memory vector engines at billion-vector scale.
2. **Standalone Vector Database (e.g. Pinecone / Qdrant):**
   - *Pros:* Highly optimized vector similarity, built-in metadata filtering.
   - *Cons:* Dual-write challenges, vendor lock-in or separate service to manage, inability to run unified PostgreSQL full-text search queries without external synchronizers.

## Decision
We select **PostgreSQL 16 with the `pgvector` extension** as our unified data store for documents, chunks, vectors, full-text indexes, and ingestion jobs.

## Consequences
- Schema migrations are tracked using Alembic.
- Full-text search and vector similarity can be executed side-by-side or combined within identical database transactions.
- Zero out-of-sync states between document text and embedding vectors.
