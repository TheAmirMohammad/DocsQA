"""Reciprocal Rank Fusion (RRF) algorithm for merging disparate search rankings."""

from dataclasses import dataclass


@dataclass
class RankedCandidate:
    chunk_id: str
    score: float
    rank: int  # 1-indexed


@dataclass
class FusedResult:
    chunk_id: str
    rrf_score: float
    vector_rank: int | None
    fts_rank: int | None
    vector_score: float | None
    fts_score: float | None


def reciprocal_rank_fusion(
    vector_results: list[tuple[str, float]],
    fts_results: list[tuple[str, float]],
    k: int = 60,
    top_n: int = 5,
    weight_vector: float = 1.0,
    weight_fts: float = 1.0,
) -> list[FusedResult]:
    """
    Combines vector search and full-text search results using Reciprocal Rank Fusion,
    with optional channel weighting.
    
    Formula: RRF_score(d) = sum_{m} w_m / (k + rank_m(d))
    
    Args:
        vector_results: List of (chunk_id, vector_similarity_score) ordered by relevance descending.
        fts_results: List of (chunk_id, fts_rank_score) ordered by relevance descending.
        k: Smoothing constant, standard default 60.
        top_n: Number of fused results to return.
        weight_vector: Multiplier for vector channel score (default 1.0).
        weight_fts: Multiplier for FTS channel score (default 1.0).
    """
    scores: dict[str, float] = {}
    vec_map: dict[str, tuple[int, float]] = {}
    fts_map: dict[str, tuple[int, float]] = {}

    for rank, (chunk_id, score) in enumerate(vector_results, start=1):
        vec_map[chunk_id] = (rank, score)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (weight_vector / (k + rank))

    for rank, (chunk_id, score) in enumerate(fts_results, start=1):
        fts_map[chunk_id] = (rank, score)
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (weight_fts / (k + rank))

    # Sort descending by fused RRF score
    sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]

    fused_results: list[FusedResult] = []
    for chunk_id, rrf_score in sorted_items:
        v_info = vec_map.get(chunk_id)
        f_info = fts_map.get(chunk_id)
        fused_results.append(
            FusedResult(
                chunk_id=chunk_id,
                rrf_score=round(rrf_score, 6),
                vector_rank=v_info[0] if v_info else None,
                fts_rank=f_info[0] if f_info else None,
                vector_score=round(v_info[1], 4) if v_info else None,
                fts_score=round(f_info[1], 4) if f_info else None,
            )
        )

    return fused_results
