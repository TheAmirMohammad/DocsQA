"""Vector similarity search using pgvector cosine distance."""

import json
import math

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def search_vector(
    session: AsyncSession,
    query_vector: list[float],
    embedding_model: str,
    embedding_version: str,
    limit: int = 20,
) -> list[tuple[Chunk, float]]:
    """
    Search chunks by vector cosine similarity.
    Uses PostgreSQL pgvector `<=>` operator when connected to Postgres,
    with an in-memory cosine fallback for SQLite/test fixtures.
    Only vectors from the query's embedding model/version are compared, so a
    half-finished re-embed never mixes incompatible vector spaces.
    """
    is_pg = session.bind and session.bind.dialect.name == "postgresql"

    if is_pg:
        # PostgreSQL pgvector query
        vec_str = "[" + ",".join(str(x) for x in query_vector) + "]"
        query = text("""
            SELECT id, (1.0 - (embedding <=> CAST(:vec AS vector))) AS similarity
            FROM chunks
            WHERE embedding IS NOT NULL
              AND embedding_model = :model AND embedding_version = :version
            ORDER BY embedding <=> CAST(:vec AS vector), content_hash
            LIMIT :limit;
        """)
        result = await session.execute(query, {"vec": vec_str, "model": embedding_model, "version": embedding_version, "limit": limit})
        rows = result.fetchall()

        if not rows:
            return []

        chunk_ids = [r[0] for r in rows]
        score_map = {r[0]: float(r[1]) for r in rows}

        chunks_res = await session.execute(
            select(Chunk).where(Chunk.id.in_(chunk_ids))
        )
        chunks_by_id = {c.id: c for c in chunks_res.scalars().all()}

        output: list[tuple[Chunk, float]] = []
        for cid in chunk_ids:
            if cid in chunks_by_id:
                output.append((chunks_by_id[cid], score_map[cid]))
        return output

    else:
        # Fallback for SQLite / unit testing without pgvector
        stmt = select(Chunk).where(
            Chunk.embedding.isnot(None),
            Chunk.embedding_model == embedding_model,
            Chunk.embedding_version == embedding_version,
        )
        res = await session.execute(stmt)
        all_chunks = res.scalars().all()

        scored: list[tuple[Chunk, float]] = []
        for c in all_chunks:
            emb = c.embedding
            if isinstance(emb, str):
                emb = json.loads(emb)
            if emb and len(emb) == len(query_vector):
                sim = cosine_similarity(query_vector, emb)
                scored.append((c, sim))

        scored.sort(key=lambda x: (-x[1], x[0].content_hash))
        return scored[:limit]
