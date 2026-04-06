# ADR-0003: Reciprocal Rank Fusion (RRF) for Hybrid Vector + Lexical Search

## Status
Accepted

## Context
Pure vector search excels at conceptual and semantic similarity (e.g., "how to validate request payloads" -> matches Pydantic schemas), but struggles with exact lexical tokens, error codes, specific function names (`Depends(get_db)`), and rare acronyms. Conversely, full-text search (BM25 or PostgreSQL `tsvector`) excels at exact tokens but fails at paraphrasing or semantic intent.

Hybrid search solves both, but combining two disparate scoring systems (cosine similarity bounded in $[0, 1]$ vs unbounded `ts_rank` or BM25 scores) presents calibration challenges.

## Decision Drivers
- **Score normalization fragility:** Normalizing cosine distance and BM25 scores linearly ($s_{norm} = \alpha s_{vec} + (1-\alpha) s_{bm25}$) requires tuning $\alpha$ and minimum/maximum normalizers that drift as the corpus changes.
- **Robustness across queries:** The rank merger must perform stably across both keyword-heavy queries and conceptual questions.
- **Computational efficiency:** The merging algorithm must be fast ($O(N \log N)$) and compute purely in memory after fetching candidates.

## Considered Options
1. **Reciprocal Rank Fusion (RRF) (Selected):**
   - Formula:
     $$RRF\_score(d) = \sum_{m \in \{vec, fts\}} \frac{1}{k + rank_m(d)}$$
     where standard constant $k=60$.
   - *Pros:* Rank-based rather than score-based; completely immune to scale and distribution differences between vector distance and lexical scores; widely validated in IR literature (Cormack et al.).
   - *Cons:* Discards the absolute magnitude of similarity, but reranking or confidence thresholding can reference the top candidate's vector score.
2. **Linear Score Combination ($\alpha$-blended):**
   - *Pros:* Preserves margin distances.
   - *Cons:* Extremely sensitive to weight parameter $\alpha$ and corpus size fluctuations.
3. **Cross-Encoder Reranker (e.g., Cohere or BAAI/bge-reranker):**
   - *Pros:* Highest potential precision.
   - *Cons:* Significant latency penalty (100-300ms additional per query) and requires either external API costs or heavy local GPU/CPU dependencies. Can be introduced as an optional pipeline stage.

## Decision
We adopt **Reciprocal Rank Fusion with $k=60$** to merge the top-$N$ vector candidates and top-$N$ full-text search candidates into a final ranked list.

## Consequences
- Queries fetch top 20 candidates from pgvector and top 20 candidates from Postgres full-text search.
- The fusion layer deduplicates candidates and sorts by their combined RRF score.
- The evaluation harness benchmarks Vector-Only, Full-Text-Only, and Hybrid (RRF) across the golden dataset to mathematically prove retrieval gains.
