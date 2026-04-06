# ADR-0004: Normalized Question Hashing with Index-Version Invalidation

## Status
Accepted

## Context
Production RAG systems suffer from latency and token expense if every repeated question executes an embedding generation, two database queries, and an LLM generation. Caching responses is essential.

However, caching in RAG introduces a notorious risk: **stale answers** when documentation is updated, deleted, or re-ingested.

## Decision Drivers
- **Deterministic lookup for equivalent queries:** Variations in capitalization, whitespace, and trivial terminal punctuation (`?`, `!`, `.`) should hit the exact same cache entry.
- **Zero-stale-guarantee on document update:** When an ingestion job updates chunks, any existing cached answer that was based on the old index must never be served.
- **O(1) invalidation overhead:** Flushing millions of individual keys using `SCAN` or pattern matching in Redis blocks Redis and degrades performance.

## Considered Options
1. **Index-Version Key Namespacing (Selected):**
   - Cache keys are namespaced by the global index version:
     `docsqa:cache:v{index_version}:{mode}:{question_hash}`
   - `index_version` lives in PostgreSQL (`system_state` row), next to the chunks it describes, so there is one source of truth; Redis only holds disposable cache entries.
   - Upon completion of any ingestion job that modifies, adds, or removes document chunks, `index_version` is incremented with a single atomic `UPDATE ... SET value = value + 1`.
   - *Pros:* Invalidation is instantaneous ($O(1)$) without scanning keys. Previous versions naturally expire based on Redis TTL.
   - *Cons:* All cache entries are invalidated when any document changes, but in documentation systems, updates are periodic batch operations and freshness guarantees outweigh selective retention.
2. **Vector-Distance-Based Cache (Exact Similarity Threshold):**
   - Compare new question embedding against a vector cache of previous questions.
   - *Pros:* Can match paraphrased questions (e.g. "What is FastAPI?" vs "Explain FastAPI").
   - *Cons:* Adds vector search overhead on the cache lookup itself; high false-positive risk for subtle nuances (e.g., "OAuth2 password flow" vs "OAuth2 auth code flow"); complex selective invalidation.
3. **Selective Graph Invalidation:**
   - Link cache entries to chunk IDs; invalidate when any linked chunk changes.
   - *Pros:* Only invalidates affected questions.
   - *Cons:* Significant bookkeeping overhead; does not invalidate questions whose answers should have changed due to *new* information being added.

## Decision
We implement a **Normalized Question Hash with Atomic Index-Version Invalidation**:
1. Normalize query text: lowercased, stripped punctuation, collapsed whitespace, SHA256 hashed.
2. Structure Redis key as `docsqa:cache:v{index_version}:{mode}:{question_hash}`; `/ask` reads `index_version` from PostgreSQL per request.
3. Atomically increment `index_version` (PostgreSQL) upon index modification. Regression test: `tests/test_api.py::test_reingest_invalidates_cached_answer`.
4. Set a safety TTL (default 24 hours).

## Consequences
- Cache hits bypass embedding and LLM generation completely, reducing response time from ~1000ms to <5ms.
- Every cache hit returns a `cached: true` flag and the `index_version` in the API debug response.
- Re-ingestion guarantees zero stale answers without running dangerous Redis `FLUSHDB` or slow pattern deletions.
