"""Evaluation metrics: retrieval hit rate, MRR, refusal accuracy, citation validity, faithfulness."""

import re
from dataclasses import dataclass, field

_STOPWORDS = {
    "based", "documentation", "with", "that", "this", "from", "have", "into", "your",
    "when", "which", "will", "also", "they", "them", "then", "than", "there", "their",
}


@dataclass
class QueryEvalResult:
    query_id: str
    question: str
    category: str
    should_refuse: bool
    actually_refused: bool
    is_hit_at_1: bool
    is_hit_at_3: bool
    is_hit_at_5: bool
    reciprocal_rank: float
    citation_valid: bool
    latency_ms: float
    top_score: float
    faithfulness: float | None = None  # None when no answer was produced
    retrieved_sources: list[str] = field(default_factory=list)


@dataclass
class ModeSummaryMetrics:
    mode: str
    total_queries: int
    answerable_queries: int
    unanswerable_queries: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float
    refusal_accuracy: float
    false_refusal_rate: float
    citation_validity_rate: float
    faithfulness: float
    avg_latency_ms: float
    p95_latency_ms: float
    hit_at_3_by_category: dict[str, float] = field(default_factory=dict)


def lexical_faithfulness(answer: str, cited_texts: list[str]) -> float:
    """
    Share of the answer's content words that appear in the cited chunks.

    A cheap, deterministic proxy for "is the answer grounded in its citations":
    it catches answers that bring in vocabulary absent from the sources, but it
    cannot detect a wrong claim built from the sources' own words.
    """
    tokens = [
        t for t in re.findall(r"[a-z0-9_]{4,}", re.sub(r"\[\d+\]", " ", answer.lower()))
        if t not in _STOPWORDS
    ]
    if not tokens:
        return 0.0
    source = " ".join(cited_texts).lower()
    return sum(1 for t in tokens if t in source) / len(tokens)


def _rate(items: list[QueryEvalResult], pred) -> float:
    return round(sum(1 for r in items if pred(r)) / len(items), 4) if items else 0.0


def compute_mode_metrics(mode: str, results: list[QueryEvalResult]) -> ModeSummaryMetrics:
    answerable = [r for r in results if not r.should_refuse]
    unanswerable = [r for r in results if r.should_refuse]
    faithful = [r.faithfulness for r in answerable if r.faithfulness is not None]

    latencies = sorted(r.latency_ms for r in results)
    p95 = latencies[min(int(0.95 * len(latencies)), len(latencies) - 1)] if latencies else 0.0

    categories = sorted({r.category for r in answerable})

    return ModeSummaryMetrics(
        mode=mode,
        total_queries=len(results),
        answerable_queries=len(answerable),
        unanswerable_queries=len(unanswerable),
        hit_at_1=_rate(answerable, lambda r: r.is_hit_at_1),
        hit_at_3=_rate(answerable, lambda r: r.is_hit_at_3),
        hit_at_5=_rate(answerable, lambda r: r.is_hit_at_5),
        mrr=round(sum(r.reciprocal_rank for r in answerable) / len(answerable), 4) if answerable else 0.0,
        refusal_accuracy=_rate(unanswerable, lambda r: r.actually_refused),
        false_refusal_rate=_rate(answerable, lambda r: r.actually_refused),
        citation_validity_rate=_rate(answerable, lambda r: r.citation_valid),
        faithfulness=round(sum(faithful) / len(faithful), 4) if faithful else 0.0,
        avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        p95_latency_ms=round(p95, 2),
        hit_at_3_by_category={
            c: _rate([r for r in answerable if r.category == c], lambda r: r.is_hit_at_3)
            for c in categories
        },
    )
