"""Unit tests for Reciprocal Rank Fusion (RRF)."""

from app.retrieval.rrf import reciprocal_rank_fusion


def test_rrf_combines_ranks_properly():
    # Chunk A: rank 1 in vector, rank 2 in fts
    # Chunk B: rank 2 in vector, not in fts
    # Chunk C: not in vector, rank 1 in fts
    vector_results = [("chunk_A", 0.95), ("chunk_B", 0.85)]
    fts_results = [("chunk_C", 0.90), ("chunk_A", 0.80)]

    fused = reciprocal_rank_fusion(vector_results, fts_results, k=60, top_n=3)

    assert len(fused) == 3
    # chunk_A is in both top ranks: (1/61) + (1/62) ≈ 0.01639 + 0.01612 = 0.03251
    # chunk_C: (1/61) ≈ 0.01639
    # chunk_B: (1/62) ≈ 0.01612
    assert fused[0].chunk_id == "chunk_A"
    assert fused[0].vector_rank == 1
    assert fused[0].fts_rank == 2
    assert fused[0].rrf_score > fused[1].rrf_score

    assert fused[1].chunk_id == "chunk_C"
    assert fused[2].chunk_id == "chunk_B"


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([], [], k=60) == []
    
    # Vector only
    fused = reciprocal_rank_fusion([("doc1", 0.9)], [], k=60)
    assert len(fused) == 1
    assert fused[0].chunk_id == "doc1"
    assert fused[0].fts_rank is None
