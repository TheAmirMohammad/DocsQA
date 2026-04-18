"""Unified retrieval engine supporting hybrid (RRF), vector-only, and full-text search with refusal."""

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk
from app.models_adapter import get_model_adapter
from app.retrieval.fts import search_fts
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.vector import search_vector

_CONTEXT_TAG = re.compile(r"<\s*/?\s*context\s*>", re.IGNORECASE)


def as_untrusted_data(text: str) -> str:
    """Strip <context> delimiters so ingested text cannot close the data block and pose as instructions."""
    while (cleaned := _CONTEXT_TAG.sub("", text)) != text:  # repeat: "</con</context>text>" reassembles
        text = cleaned
    return text


@dataclass
class Citation:
    index: int
    source_url: str
    heading: str
    chunk_id: str


@dataclass
class RetrievedChunkDebug:
    chunk_id: str
    heading: str
    source_url: str
    content: str
    score: float
    vector_rank: int | None = None
    fts_rank: int | None = None


@dataclass
class RetrievalResponse:
    answer: str
    citations: list[Citation]
    refused: bool
    retrieval_mode: str
    top_score: float
    retrieved_chunks: list[RetrievedChunkDebug]


class RetrievalEngine:
    """Core retrieval engine coordinating vector search, full-text search, RRF fusion, and generation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.adapter = get_model_adapter()

    async def query(
        self,
        query_text: str,
        mode: Literal["hybrid", "vector", "fts"] = "hybrid",
        top_k: int = settings.RETRIEVAL_TOP_K,
    ) -> RetrievalResponse:
        clean_query = query_text.strip()
        if not clean_query:
            return RetrievalResponse(
                answer="I do not have sufficient information in the documentation to answer this question.",
                citations=[],
                refused=True,
                retrieval_mode=mode,
                top_score=0.0,
                retrieved_chunks=[],
            )

        # 1. Fetch candidates according to mode
        vector_candidates: list[tuple[Chunk, float]] = []
        fts_candidates: list[tuple[Chunk, float]] = []

        if mode in ("hybrid", "vector"):
            query_vec = await self.adapter.embed_query(clean_query)
            if query_vec:
                vector_candidates = await search_vector(
                    self.session,
                    query_vec,
                    embedding_model=self.adapter.model_name,
                    embedding_version=self.adapter.model_version,
                    limit=settings.RETRIEVAL_VECTOR_CANDIDATES,
                )

        if mode in ("hybrid", "fts"):
            fts_candidates = await search_fts(
                self.session, clean_query, limit=settings.RETRIEVAL_FTS_CANDIDATES
            )

        # Weak-evidence floor: drop candidates below the similarity/lexical floors.
        # Nothing left means refuse (RRF scores are rank-based, not a confidence signal).
        vector_candidates = [(c, s) for c, s in vector_candidates if s >= settings.VECTOR_MIN_SIMILARITY]
        fts_candidates = [(c, s) for c, s in fts_candidates if s > 0.0]

        # 2. Rank candidates
        selected_chunks: list[tuple[Chunk, float, int | None, int | None]] = []

        if mode == "hybrid":
            vec_pairs = [(c.id, score) for c, score in vector_candidates]
            fts_pairs = [(c.id, score) for c, score in fts_candidates]
            fused = reciprocal_rank_fusion(
                vec_pairs, fts_pairs, k=settings.RRF_K, top_n=top_k
            )

            # Map chunk IDs to objects
            all_chunks_map = {c.id: c for c, _ in vector_candidates}
            all_chunks_map.update({c.id: c for c, _ in fts_candidates})

            # If any fused IDs missing from candidate maps, fetch from DB
            missing_ids = [f.chunk_id for f in fused if f.chunk_id not in all_chunks_map]
            if missing_ids:
                res = await self.session.execute(
                    select(Chunk).where(Chunk.id.in_(missing_ids))
                )
                for c in res.scalars().all():
                    all_chunks_map[c.id] = c

            for item in fused:
                if item.chunk_id in all_chunks_map:
                    selected_chunks.append((
                        all_chunks_map[item.chunk_id],
                        item.rrf_score,
                        item.vector_rank,
                        item.fts_rank,
                    ))

        elif mode == "vector":
            for rank, (c, score) in enumerate(vector_candidates[:top_k], start=1):
                selected_chunks.append((c, score, rank, None))

        elif mode == "fts":
            for rank, (c, score) in enumerate(fts_candidates[:top_k], start=1):
                selected_chunks.append((c, score, None, rank))

        # 3. Check for confidence and refusal
        top_score = selected_chunks[0][1] if selected_chunks else 0.0
        # Kept on every path, refusals included: lets /ask callers and the eval harness see
        # what retrieval found even when the generator declines to answer
        debug_chunks = [
            RetrievedChunkDebug(
                chunk_id=c.id,
                heading=c.heading,
                source_url=c.source_url,
                content=c.content[:200] + ("..." if len(c.content) > 200 else ""),
                score=round(score, 4),
                vector_rank=v_rank,
                fts_rank=f_rank,
            )
            for c, score, v_rank, f_rank in selected_chunks
        ]

        if not selected_chunks:
            return RetrievalResponse(
                answer="I do not have sufficient information in the documentation to answer this question.",
                citations=[],
                refused=True,
                retrieval_mode=mode,
                top_score=round(top_score, 4),
                retrieved_chunks=debug_chunks,
            )

        # 4. Construct prompt context with citation anchors
        context_parts = []
        citations_registry: list[Citation] = []

        for idx, (chunk, score, v_rank, f_rank) in enumerate(selected_chunks, start=1):
            context_parts.append(
                f"[Chunk {idx}: {as_untrusted_data(chunk.source_url)} # {as_untrusted_data(chunk.heading)}]\n"
                f"{as_untrusted_data(chunk.content)}"
            )
            citations_registry.append(
                Citation(
                    index=idx,
                    source_url=chunk.source_url,
                    heading=chunk.heading,
                    chunk_id=chunk.id,
                )
            )

        context_str = "\n\n".join(context_parts)

        # 5. Generate answer using model adapter
        answer = await self.adapter.generate(prompt=clean_query, context=context_str)

        # Check if the generator itself determined the context is insufficient
        if "insufficient information" in answer.lower() or "do not have sufficient" in answer.lower():
            return RetrievalResponse(
                answer="I do not have sufficient information in the documentation to answer this question.",
                citations=[],
                refused=True,
                retrieval_mode=mode,
                top_score=round(top_score, 4),
                retrieved_chunks=debug_chunks,
            )

        # Filter citations to only those actually cited in the answer (e.g. [1], [2])
        cited_indices = [int(m) for m in re.findall(r"\[(\d+)\]", answer)]
        if cited_indices:
            filtered_citations = [
                c for c in citations_registry if c.index in set(cited_indices)
            ]
        else:
            filtered_citations = citations_registry[:2]

        return RetrievalResponse(
            answer=answer,
            citations=filtered_citations,
            refused=False,
            retrieval_mode=mode,
            top_score=round(top_score, 4),
            retrieved_chunks=debug_chunks,
        )
