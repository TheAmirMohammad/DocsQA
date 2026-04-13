"""Model adapter registry and factory."""

from functools import lru_cache

from app.config import settings
from app.models_adapter.base import BaseModelAdapter
from app.models_adapter.ollama_adapter import OllamaModelAdapter
from app.models_adapter.openai_adapter import OpenAIModelAdapter
from app.models_adapter.stub import StubModelAdapter


@lru_cache(maxsize=1)
def get_model_adapter() -> BaseModelAdapter:
    """Return the configured model adapter singleton."""
    provider = settings.MODEL_PROVIDER.lower()
    if provider == "openai":
        return OpenAIModelAdapter()
    elif provider == "ollama":
        return OllamaModelAdapter()
    else:
        return StubModelAdapter(
            dimension=settings.EMBEDDING_DIMENSION,
            model_version=settings.EMBEDDING_MODEL_VERSION,
        )
