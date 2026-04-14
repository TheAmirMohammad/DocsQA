"""Base model adapter interface for embeddings and answer generation."""

from abc import ABC, abstractmethod


class BaseModelAdapter(ABC):
    """Abstract interface for LLM providers (Hosted, Local, and Stub)."""

    def __init__(self, model_name: str, model_version: str, dimension: int):
        self.model_name = model_name
        self.model_version = model_version
        self.dimension = dimension

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute unit-normalized vector embeddings for a batch of texts."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query. Override for models that embed queries and documents differently."""
        return (await self.embed([text]))[0]

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> str:
        """Generate answer response given query and retrieved context."""
