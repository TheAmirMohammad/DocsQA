"""Configuration management for DocsQA using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    PROJECT_NAME: str = "DocsQA"
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/docsqa"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # Redis (Cache & ARQ)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Model Provider: stub, openai, ollama
    MODEL_PROVIDER: Literal["stub", "openai", "ollama"] = "stub"

    # OpenAI Settings
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_CHAT_MODEL: str = "llama3.2"

    # Embeddings
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_MODEL_VERSION: str = "stub-v1.0"

    # Retrieval & Fusion
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_VECTOR_CANDIDATES: int = 20
    RETRIEVAL_FTS_CANDIDATES: int = 20
    RRF_K: int = 60
    RRF_WEIGHT_VECTOR: float = 0.6  # Default weight for vector similarity in weighted RRF
    RRF_WEIGHT_FTS: float = 0.4     # Default weight for full-text search in weighted RRF
    VECTOR_MIN_SIMILARITY: float = 0.15  # cosine floor; below it a chunk is not evidence
    RERANKER_ENABLED: bool = False
    RERANKER_TOP_K: int = 5

    # Semantic Cache
    CACHE_TTL_SECONDS: int = 86400

    # Ingestion Defaults
    SAMPLE_DOCS_PATH: str = "./sample_docs/fastapi_tutorial"
    DOCS_ROOT: str = "./sample_docs"  # POST /ingest may only read directories under this root
    CHUNK_MAX_WORDS: int = 400  # sections longer than this split between blocks


settings = Settings()
