"""Prometheus metrics instrumentation for DocsQA."""

from prometheus_client import Counter, Gauge, Histogram

QUERY_LATENCY = Histogram(
    "docsqa_query_latency_seconds",
    "Time spent processing query and generating answer in seconds",
    ["mode", "cached"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

QUERIES_TOTAL = Counter(
    "docsqa_queries_total",
    "Total queries received",
    ["mode", "status", "cached"],
)

CACHE_HITS_TOTAL = Counter(
    "docsqa_cache_hits_total",
    "Total cache hits for query retrieval",
)

CACHE_MISSES_TOTAL = Counter(
    "docsqa_cache_misses_total",
    "Total cache misses for query retrieval",
)

REFUSALS_TOTAL = Counter(
    "docsqa_refusals_total",
    "Total queries where model refused to guess due to low context confidence",
)

CHUNKS_INDEXED_TOTAL = Gauge(
    "docsqa_chunks_indexed_total",
    "Total documentation chunks currently present in pgvector index",
)

INGESTION_JOBS_TOTAL = Counter(
    "docsqa_ingestion_jobs_total",
    "Total ingestion jobs executed",
    ["status"],
)
