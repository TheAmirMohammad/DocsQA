"""Full-text search using PostgreSQL tsvector with an OR-of-terms tsquery ranked by ts_rank_cd."""

import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk


async def search_fts(
    session: AsyncSession,
    query_text: str,
    limit: int = 20,
) -> list[tuple[Chunk, float]]:
    """
    Search chunks using PostgreSQL full-text search with ts_rank_cd.
    Falls back to lexical keyword matching on non-Postgres engines.
    """
    if not query_text or not query_text.strip():
        return []

    is_pg = session.bind and session.bind.dialect.name == "postgresql"

    if is_pg:
        # Questions are prose, so AND-ing every term (websearch/plainto_tsquery) almost never
        # matches one section. OR the stemmed terms and let ts_rank_cd reward coverage.
        query = text("""
            WITH q AS (
                SELECT NULLIF(replace(plainto_tsquery('english', :q)::text, ' & ', ' | '), '')::tsquery AS tsq
            )
            SELECT id, ts_rank_cd(tsv, q.tsq) AS rank
            FROM chunks, q
            WHERE tsv @@ q.tsq
            ORDER BY rank DESC, content_hash  -- ties are common; uuid order would differ per DB
            LIMIT :limit;
        """)
        result = await session.execute(query, {"q": query_text, "limit": limit})
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
        # Fallback for SQLite / unit testing without Postgres tsvector
        words = set(re.findall(r"\b\w{3,}\b", query_text.lower()))
        if not words:
            return []

        stmt = select(Chunk)
        res = await session.execute(stmt)
        all_chunks = res.scalars().all()

        scored: list[tuple[Chunk, float]] = []
        for c in all_chunks:
            c_text = (c.content + " " + c.heading).lower()
            matches = sum(1 for w in words if w in c_text)
            if matches > 0:
                score = matches / len(words)
                scored.append((c, score))

        scored.sort(key=lambda x: (-x[1], x[0].content_hash))
        return scored[:limit]
