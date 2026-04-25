"""Pydantic schemas for API request and response validation."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="The technical question to answer from documentation.")
    mode: Literal["hybrid", "vector", "fts"] = Field(
        default="hybrid",
        description="Retrieval strategy: 'hybrid' (vector + FTS with RRF), 'vector' (pgvector only), or 'fts' (Postgres full-text search only).",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum number of context chunks to retrieve.")
    bypass_cache: bool = Field(default=False, description="Whether to bypass semantic response cache.")


class CitationSchema(BaseModel):
    index: int
    source_url: str
    heading: str
    chunk_id: str


class RetrievedChunkDebugSchema(BaseModel):
    chunk_id: str
    heading: str
    source_url: str
    content_preview: str
    score: float
    vector_rank: int | None = None
    fts_rank: int | None = None


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationSchema]
    refused: bool
    cached: bool
    index_version: int
    latency_ms: float
    retrieval_mode: str
    debug: dict[str, Any] | None = None


class IngestRequest(BaseModel):
    source_path: str | None = Field(
        default=None,
        description="Relative or absolute path to docs directory. Defaults to configured SAMPLE_DOCS_PATH.",
    )


class IngestResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    source_path: str
    status: str
    docs_scanned: int
    docs_modified: int
    chunks_created: int
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class DocumentItemSchema(BaseModel):
    id: str
    source_path: str
    title: str
    content_hash: str
    chunks_count: int
    updated_at: str


class DocumentsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    documents: list[DocumentItemSchema]


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    index_version: int
    environment: str
