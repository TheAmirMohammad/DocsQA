# DocsQA: a RAG API with an evaluation harness

DocsQA is a question-answering API over technical documentation. It returns answers with inline citations to the source sections, and it refuses to answer when the retrieved evidence is weak. Most RAG demos are notebooks with no way to tell whether a change made answers better or worse. DocsQA ships with a hand-labelled golden set and a CI gate. On every pull request the gate re-runs retrieval against a stored baseline and fails the build if quality drops.

Stack: FastAPI · PostgreSQL 17 + pgvector · Redis 7 · ARQ worker · SQLAlchemy 2 + Alembic · Prometheus + Grafana · pytest, ruff and mypy on GitHub Actions.

## Architecture

```mermaid
graph TD
    Client["Client / CI"] -->|POST /ask, /ingest| API["FastAPI (api:8000)"]

    subgraph Storage
        Redis[("Redis<br/>answer cache · ARQ job queue")]
        PG[("PostgreSQL + pgvector<br/>documents · chunks (vector + tsvector)<br/>index_version · jobs · query logs")]
    end

    Worker["ARQ worker<br/>chunk · hash · embed"]

    subgraph Models["Model adapter"]
        Stub["Deterministic stub (tests, CI)"]
        OpenAI["Hosted (OpenAI-compatible)"]
        Ollama["Local (Ollama)"]
    end

    API -->|"1. read index_version"| PG
    API -->|"2. cache v{index_version}:{mode}:{hash(question)}"| Redis
    API -->|"3. vector + full-text candidates"| PG
    API -->|"4. RRF fusion, refusal check, generate"| Models
    API -->|enqueue ingestion| Redis
    Redis --> Worker
    Worker -->|embed changed files only| Models
    Worker -->|upsert chunks, bump index_version| PG

    Prom["Prometheus :9090"] -->|scrape /metrics| API
    Grafana["Grafana :3000"] --> Prom
```

## Quickstart

```bash
docker compose up --build
```

The api container runs `alembic upgrade head`, ingests `sample_docs/fastapi_tutorial`, and then starts serving. First boot takes a few seconds once images are built.

```bash
curl -s localhost:8000/healthz
curl -s -XPOST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "How does OAuth2PasswordBearer extract tokens?", "mode": "hybrid", "top_k": 3}'
```

- API docs: http://localhost:8000/docs (spec committed as [`openapi.json`](openapi.json))
- Grafana: http://localhost:3000 (admin/admin). The "DocsQA RAG Engine Observability" dashboard is provisioned automatically.
- Prometheus: http://localhost:9090

Local development without Docker:

```bash
uv sync --all-groups
uv run pytest                              # SQLite, no services needed
uv run ruff check . && uv run mypy
docker compose up -d postgres redis        # for evals / the real retrieval paths
uv run alembic upgrade head
uv run python scripts/run_evals.py         # runs the golden set and the baseline gate
```

The default model is the deterministic stub. Set `MODEL_PROVIDER=openai` or `ollama` in `.env` (see [`.env.example`](.env.example)). `EMBEDDING_DIMENSION` must match the embedding model (stub 384, nomic-embed-text 768). The migration creates `vector(EMBEDDING_DIMENSION)`, so use a fresh database when switching (see *With real models*).

## API

| Endpoint | Purpose |
|---|---|
| `POST /ask` | Question in; answer, citations, `refused` flag, `cached` flag, and retrieval debug data (per-chunk vector rank, FTS rank, fused score) out. `mode` is `hybrid`, `vector` or `fts`. |
| `POST /ingest` | Queue incremental ingestion of a directory under `DOCS_ROOT`. Returns a job id; other paths return 400. |
| `GET /jobs/{id}` | Ingestion status: files scanned, files changed, chunks written, errors. |
| `GET /documents` | Indexed documents with content hashes and chunk counts. |
| `GET /evals/latest` | Most recent evaluation report (JSON and Markdown). |
| `GET /healthz` | PostgreSQL, Redis and current index version. |
| `GET /metrics` | Prometheus metrics. |

A refused answer looks like `{"answer": "I do not have sufficient information in the documentation to answer this question.", "citations": [], "refused": true, ...}`.

## Measured results

Measured with `scripts/run_evals.py` on PostgreSQL 17 + pgvector, with the deterministic stub model, over the expanded 60-question golden set ([`evals/dataset.json`](evals/dataset.json)): 33 single-section lookups, 15 multi-section questions and 12 out-of-scope / adversarial questions that must be refused. A hit means a top-k chunk comes from an expected file **and** an expected section. Full report: [`evals/latest_report.md`](evals/latest_report.md).

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal accuracy | False refusals | Valid citations | Lex. Faith. | LLM Faith. |
|---|---|---|---|---|---|---|---|---|---|
| Vector only | 31.2% | 50.0% | 60.4% | 0.417 | 100.0% | 16.7% | 83.3% | 93.3% | 80.2% |
| Full-text only | 60.4% | 83.3% | 91.7% | 0.724 | 91.7% | 4.2% | 95.8% | 94.4% | 86.6% |
| Hybrid (RRF, k=60) | 47.9% | 66.7% | 77.1% | 0.593 | 100.0% | 8.3% | 91.7% | 96.3% | 90.1% |
| Hybrid (Weighted) | 50.0% | 66.7% | 72.9% | 0.590 | 100.0% | 8.3% | 91.7% | 96.7% | 89.6% |
| Hybrid (Reranked) | 58.3% | 83.3% | 85.4% | 0.702 | 91.7% | 6.2% | 93.8% | 96.7% | 86.0% |

This stub run is what CI gates on: deterministic, free, no GPU. Its embedder is feature-hashed bag-of-words with no semantics, so the vector and hybrid rows say little about real retrieval. They exist to catch regressions.

### With real models

The same golden set and harness, run once locally with Ollama: `nomic-embed-text` (768-d, with its `search_query:`/`search_document:` task prefixes) for embeddings and `llama3.2` (3B) for answers. Hardware was an Apple M2 Pro. Full report: [`evals/reports/ollama_nomic_llama3.2.md`](evals/reports/ollama_nomic_llama3.2.md).

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal accuracy | False refusals | Faithfulness (lexical) | P95 latency |
|---|---|---|---|---|---|---|---|---|
| Vector only | 75.0% | 95.0% | 97.5% | 0.852 | 100% | 15.0% | 64.5% | 6.7 s |
| Full-text only | 52.5% | 80.0% | 87.5% | 0.667 | 100% | 27.5% | 60.9% | 6.1 s |
| Hybrid (RRF, k=60) | 70.0% | 92.5% | 92.5% | 0.800 | 100% | 20.0% | 63.9% | 7.4 s |

What this shows, and what it doesn't:
- **Real embeddings change the ranking.** Vector-only goes from 55% to 95% Hit@3, and full-text is now the weakest mode.
- **Hybrid did not beat vector-only here.** It ties on multi-section questions (93.3% Hit@3) and is slightly behind overall. The golden questions are mostly paraphrases, which favour dense retrieval. The OR-style full-text query also brings in loosely matching chunks that unweighted RRF then promotes. Weighted RRF, or a reranker, is the next experiment, and the harness will say whether it helps.
- **Refusal comes from the generator.** Every out-of-scope question was refused, but llama3.2 also refused 15–27% of *answerable* ones. That is the current weak spot, and it is a prompt/model problem, not a retrieval problem: hits are scored on what was retrieved, even when the generator then declined.
- Latency is dominated by local generation on a laptop. It is not a server benchmark.
- 50 questions over 39 chunks of a small hand-written corpus is a small sample. One question is 2.5 points.

Reproduce (needs `ollama pull nomic-embed-text llama3.2`):

```bash
docker exec docsqa-postgres psql -U postgres -c "CREATE DATABASE docsqa_ollama"
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/docsqa_ollama \
       MODEL_PROVIDER=ollama EMBEDDING_DIMENSION=768
uv run alembic upgrade head
uv run python scripts/run_evals.py --no-gate --report evals/reports/ollama_nomic_llama3.2.md
```

### The CI gate

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs ruff, mypy and pytest. It then runs the eval suite against a Postgres service container and compares every mode with [`evals/baseline.json`](evals/baseline.json). Any drop in Hit@3, MRR, refusal accuracy or faithfulness, or any rise in false refusals, fails the build. Because the stub is deterministic, a single question regressing (1/40 = 2.5 points) is enough to fail. The baseline records its environment (database, provider, embedding model), and the gate refuses to compare numbers across environments. Retrieval breaks score ties by `content_hash`, not by the random chunk ids, so a fresh database reproduces the baseline exactly. This was verified by baselining on one fresh Postgres volume and passing the gate on another.

To accept an intended change in quality, run `uv run python scripts/run_evals.py --update-baseline` and commit `evals/baseline.json` with the PR, so the reviewer sees the diff.

## Engineering traps and how they are handled

- **Chunk boundaries.** [`app/ingestion/chunker.py`](app/ingestion/chunker.py) parses Markdown into blocks (fenced code, tables, paragraphs, headings) with a line scanner. It makes one chunk per heading section and splits long sections only *between* blocks, so a code block or table is never cut, even when it is larger than the chunk limit. Each chunk carries its heading breadcrumb, and the citation anchor points at the section the text actually came from. Tests: `tests/test_chunker.py`.
- **Stale cache after re-ingest.** Cache keys are `docsqa:cache:v{index_version}:{mode}:{sha256(normalized question)}`. `index_version` lives in PostgreSQL next to the chunks. Any ingestion that changes the index bumps it with one atomic `UPDATE`, so old entries become unreachable and expire through their TTL, with no `SCAN`/`DEL`. Regression test: `tests/test_api.py::test_reingest_invalidates_cached_answer`. ([ADR-0004](docs/decisions/ADR-0004-normalized-semantic-cache-invalidation.md))
- **Incremental ingestion.** Files are SHA-256 hashed, and unchanged files are skipped without re-embedding. Deleted files are pruned, but only within the source directory being ingested.
- **Embedding model changes.** Every chunk stores `embedding_model` and `embedding_version`. A file is re-embedded when its text changes *or* when its chunks were embedded by a different model than the active one. Vector search only compares vectors from the query's model, so a half-finished re-embed never mixes vector spaces. Test: `test_embedding_model_change_forces_reembed`.
- **Prompt injection in ingested docs.** Retrieved text is wrapped in `<context>` tags, and the system prompt says it is data, not instructions. Any `<context>`/`</context>` tag inside the documents is stripped first (`as_untrusted_data`), so a document cannot close the data block and pose as instructions. This limits the damage but does not make injection impossible. A model can still be persuaded by text inside the block.
- **Refusal.** This works at two layers. (1) Retrieval floor: candidates under `VECTOR_MIN_SIMILARITY`, or with no full-text match, are dropped, and if nothing survives the API refuses. (2) Generator: the answer is treated as refused when the model says the context is insufficient. RRF scores are deliberately *not* used as confidence, because they encode rank only. Be aware that the floor is loose: the OR full-text query matches any shared term, and real embeddings rarely fall under 0.15. In practice, refusal on out-of-scope questions comes mostly from layer 2. With llama3.2, refusal accuracy was 100% but false refusals were 15–27% (see *With real models*).
- **`/ingest` as a trust boundary.** Only directories under `DOCS_ROOT` are accepted. The resolved path is what gets handed to the worker, and symlinked files are skipped. Documents are identified by their path relative to `DOCS_ROOT`, so two sources never collide or prune each other.
- **Failed ingests.** If a job fails after some files were already committed, it still indexes those files for full-text search and bumps `index_version`, so cached answers never outlive a partial change. Test: `test_failed_ingest_still_invalidates_cache`. The ARQ worker runs one job at a time, with a 30-minute timeout.

## Observability

- JSON structured logs (structlog) with a per-request `X-Request-ID`.
- `/metrics`: `docsqa_query_latency_seconds` (by mode and cache status), `docsqa_queries_total`, `docsqa_cache_hits_total` / `docsqa_cache_misses_total`, `docsqa_refusals_total`, `docsqa_chunks_indexed_total` and `docsqa_ingestion_jobs_total`.
- Grafana dashboard: [`monitoring/grafana/dashboards/docsqa-dashboard.json`](monitoring/grafana/dashboards/docsqa-dashboard.json), provisioned together with its Prometheus datasource.

Design decisions are recorded in [`docs/decisions/`](docs/decisions/).

## Limitations

- **CI gates on the stub model only.** The real-model numbers come from one local run and are not re-checked on each PR, because that would need a GPU runner.
- **llama3.2 over-refuses** 15–27% of answerable questions (see above).
- **The corpus is small and hand-written.** `sample_docs/` holds 10 short pages summarising FastAPI tutorial topics (39 chunks), not the upstream docs. With this few chunks, hit rates are optimistic compared with a real documentation set.
- **Multi-format ingestion:** Ingests Markdown (`.md`), HTML (`.html`, `.htm`), and reStructuredText (`.rst`, `.rest`) with hierarchical heading breadcrumb tracking.
- **Git repository ingestion:** Ingests directly from remote git repositories (`git_url`, `branch`, `subpath`) via shallow clone into sandboxed doc directories.
- **Post-retrieval reranking:** Supports optional cross-encoder neural reranking and zero-overhead lexical-semantic candidate reranking.
- **LLM-judged faithfulness & injection test suite:** Statements are decomposed and verified against context chunks; adversarial jailbreak vectors are quarantined and refused.
- **Ingestion is only serialized in the ARQ worker.** The inline fallback (used when Redis is down), `seed_docs.py` and the eval runner take no lock.
- **Changing the chunker does not re-chunk unchanged files.** Only content or embedding-model changes trigger re-processing. Rebuild the index after changing the chunker.
- **The cache is exact-match**, after normalisation (case, whitespace, trailing punctuation). Paraphrases miss.
- **Full-text search uses the English configuration** (`to_tsvector('english', ...)`).

## What I would do next

1. Stream answers via Server-Sent Events (SSE) or WebSockets to minimize time-to-first-token.
2. Multi-hop agentic query expansion (Hypothetical Document Embeddings - HyDE) for complex nested documentation questions.
3. Distributed multi-worker cluster with horizontal ARQ autoscaling and S3 document blob replication.

## License

MIT, see [LICENSE](LICENSE).
