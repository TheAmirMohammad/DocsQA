"""Cross-Encoder and lexical-semantic reranker for post-retrieval candidate refinement."""

import math
import re
from abc import ABC, abstractmethod

from app.config import settings
from app.db.models import Chunk
from app.observability.logging import logger


class BaseReranker(ABC):
    """Abstract base class for chunk reranking."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[tuple[Chunk, float, int | None, int | None]],
        top_k: int = 5,
    ) -> list[tuple[Chunk, float, int | None, int | None]]:
        """Rerank candidate chunks by query relevance and return top_k."""


class LexicalSemanticReranker(BaseReranker):
    """
    High-precision, zero-overhead reranker combining exact title matching,
    query term density, contiguous phrase scoring, and prior retrieval signals.
    Does not require downloading multi-gigabyte neural weights, guaranteeing fast offline execution.
    """

    async def rerank(
        self,
        query: str,
        candidates: list[tuple[Chunk, float, int | None, int | None]],
        top_k: int = 5,
    ) -> list[tuple[Chunk, float, int | None, int | None]]:
        if not candidates or len(candidates) <= 1:
            return candidates[:top_k]

        clean_query = query.lower().strip()
        query_words = set(re.findall(r"\b\w{3,}\b", clean_query))
        if not query_words:
            return candidates[:top_k]

        scored: list[tuple[float, tuple[Chunk, float, int | None, int | None]]] = []

        for chunk, initial_score, v_rank, f_rank in candidates:
            heading_lower = chunk.heading.lower()
            content_lower = chunk.content.lower()

            # 1. Exact phrase match in heading or body
            phrase_score = 0.0
            if clean_query in heading_lower:
                phrase_score += 1.5
            elif clean_query in content_lower:
                phrase_score += 0.8

            # 2. Heading term coverage
            heading_words = set(re.findall(r"\b\w{3,}\b", heading_lower))
            matched_heading = query_words & heading_words
            heading_coverage = len(matched_heading) / len(query_words) if query_words else 0.0

            # 3. Content term coverage and density
            content_words = set(re.findall(r"\b\w{3,}\b", content_lower))
            matched_content = query_words & content_words
            content_coverage = len(matched_content) / len(query_words) if query_words else 0.0

            # 4. Proximity: count total occurrences of query terms in content
            total_occurrences = 0
            for w in query_words:
                total_occurrences += content_lower.count(w)
            density = min(total_occurrences / max(len(content_words), 1), 0.2) * 5.0

            # Combined reranking score
            # Prior retrieval score normalized (sigmoid-like scaling)
            prior_signal = math.tanh(initial_score * 50.0) if initial_score < 0.1 else min(initial_score, 1.0)
            
            rerank_score = (
                phrase_score * 0.35
                + heading_coverage * 0.25
                + content_coverage * 0.25
                + density * 0.10
                + prior_signal * 0.05
            )

            scored.append((rerank_score, (chunk, rerank_score, v_rank, f_rank)))

        # Sort descending by rerank score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]


class CrossEncoderReranker(BaseReranker):
    """
    Neural cross-encoder reranker using sentence-transformers CrossEncoder.
    Falls back gracefully to LexicalSemanticReranker if sentence-transformers is unavailable.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._fallback = LexicalSemanticReranker()
        self._init_attempted = False

    def _get_model(self):
        if not self._init_attempted:
            self._init_attempted = True
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info("Initialized neural CrossEncoder reranker", model=self.model_name)
            except Exception as e:
                logger.warning(
                    "sentence-transformers not available or failed to load, using LexicalSemanticReranker",
                    error=str(e),
                )
                self._model = None
        return self._model

    async def rerank(
        self,
        query: str,
        candidates: list[tuple[Chunk, float, int | None, int | None]],
        top_k: int = 5,
    ) -> list[tuple[Chunk, float, int | None, int | None]]:
        model = self._get_model()
        if not model or not candidates:
            return await self._fallback.rerank(query, candidates, top_k=top_k)

        try:
            pairs = [[query, f"{c.heading}\n{c.content}"] for c, _, _, _ in candidates]
            scores = model.predict(pairs)

            ranked = []
            for (chunk, _, v_rank, f_rank), score in zip(candidates, scores, strict=False):
                norm_score = float(score)
                ranked.append((norm_score, (chunk, round(norm_score, 4), v_rank, f_rank)))

            ranked.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in ranked[:top_k]]
        except Exception as e:
            logger.warning("Neural cross-encoder prediction failed, falling back to lexical reranker", error=str(e))
            return await self._fallback.rerank(query, candidates, top_k=top_k)


def get_reranker() -> BaseReranker:
    """Factory creating configured reranker instance."""
    if settings.RERANKER_ENABLED:
        return CrossEncoderReranker()
    return LexicalSemanticReranker()
