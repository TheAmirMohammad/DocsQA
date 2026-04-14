"""Deterministic stub model adapter for fast, reproducible, offline tests and CI evals."""

import hashlib
import math
import random
import re

from app.models_adapter.base import BaseModelAdapter


class StubModelAdapter(BaseModelAdapter):
    """
    Deterministic stub adapter:
    - Generates reproducible, unit-normalized vector embeddings using feature hashing
      projected into dimension D.
    - Generates grounded, cited answers based on retrieved context, or refuses when context is inadequate.
    """

    def __init__(self, dimension: int = 384, model_version: str = "stub-v1.0"):
        super().__init__(
            model_name="stub-embedding",
            model_version=model_version,
            dimension=dimension,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            vec = self._compute_deterministic_vector(text)
            embeddings.append(vec)
        return embeddings

    def _compute_deterministic_vector(self, text: str) -> list[float]:
        # Clean and tokenize
        words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
        vec = [0.0] * self.dimension
        if not words:
            # Random unit vector for empty text
            return [1.0 / math.sqrt(self.dimension)] * self.dimension

        for word in words:
            # Map word to pseudo-random seed
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16)
            rng = random.Random(h)
            for i in range(min(5, self.dimension)):
                idx = rng.randint(0, self.dimension - 1)
                sign = 1.0 if rng.random() > 0.5 else -1.0
                vec[idx] += sign

        # Compute L2 norm
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec = [1.0 / math.sqrt(self.dimension)] * self.dimension
        return vec

    async def generate(
        self,
        prompt: str,
        context: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        if not context or not context.strip():
            return "I do not have sufficient information in the documentation to answer this question."

        # Extract source citations from context headers like [Source: /path/file.md # Heading]
        sources = re.findall(r"\[(?:Source|Chunk \d+):\s*([^\]]+)\]", context)
        citations = []
        for i, s in enumerate(sources[:3], start=1):
            citations.append(f"[{i}] {s.strip()}")

        prompt_words = set(re.findall(r"\b\w{3,}\b", prompt.lower()))
        stopwords = {
            "what", "when", "where", "which", "who", "whom", "this", "that",
            "these", "those", "have", "has", "how", "does", "the", "for",
            "with", "from", "are", "you", "and", "can", "using"
        }
        meaningful_prompt_words = prompt_words - stopwords
        if not meaningful_prompt_words:
            meaningful_prompt_words = prompt_words

        # Check overall prompt topical coverage across the entire context
        context_words = set(re.findall(r"\b\w{3,}\b", context.lower()))
        matched_prompt_words = meaningful_prompt_words & context_words
        coverage = len(matched_prompt_words) / len(meaningful_prompt_words) if meaningful_prompt_words else 0.0

        # If zero keywords match, or coverage < 0.30 for multi-keyword queries (3+ keywords), context is insufficient
        if not matched_prompt_words:
            return "I do not have sufficient information in the documentation to answer this question."
        if len(meaningful_prompt_words) >= 3 and coverage < 0.30:
            return "I do not have sufficient information in the documentation to answer this question."

        relevant_sentences = []
        for line in context.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith(("#", "[")):
                continue
            line_words = set(re.findall(r"\b\w{3,}\b", line_str.lower()))
            if meaningful_prompt_words & line_words:
                relevant_sentences.append(line_str)
            if len(relevant_sentences) >= 3:
                break

        if not relevant_sentences:
            return "I do not have sufficient information in the documentation to answer this question."

        body = " ".join(relevant_sentences)
        citation_tags = " ".join(f"[{i}]" for i in range(1, min(3, len(sources) + 1))) or "[1]"
        
        answer = f"Based on the documentation, {body} {citation_tags}"
        return answer
