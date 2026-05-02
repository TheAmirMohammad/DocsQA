"""Tests for question caching and index-version invalidation."""

import pytest

from app.cache.redis_cache import QuestionCache
from app.ingestion.hasher import normalize_query_for_cache


def test_query_normalization():
    q1 = "How does FastAPI handle dependency injection??"
    q2 = "  how does   fastapi handle dependency injection?  "
    q3 = "how does fastapi handle dependency injection."

    assert normalize_query_for_cache(q1) == "how does fastapi handle dependency injection"
    assert normalize_query_for_cache(q2) == "how does fastapi handle dependency injection"
    assert normalize_query_for_cache(q3) == "how does fastapi handle dependency injection"


@pytest.mark.asyncio
async def test_cache_set_get_and_invalidation():
    cache = QuestionCache(redis_url="redis://localhost:9999/0")  # memory fallback when offline

    query = "How to define path parameters?"
    data = {"answer": "Use curly braces in path decorator.", "citations": []}

    assert await cache.get(query, "hybrid", 1) is None
    await cache.set(query, "hybrid", 1, data)

    hit = await cache.get("  how to define PATH parameters ", "hybrid", 1)
    assert hit is not None
    assert hit["answer"] == data["answer"]

    # Different mode or a newer index version must miss
    assert await cache.get(query, "fts", 1) is None
    assert await cache.get(query, "hybrid", 2) is None
