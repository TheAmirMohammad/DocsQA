"""Database models for DocsQA using SQLAlchemy 2.0 and pgvector."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.config import settings

try:
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:
    PgVector = None  # type: ignore


class Base(DeclarativeBase):
    """Base declarative class with type annotation support."""


class VectorType(TypeDecorator):
    """Platform-independent vector type that falls back to JSON when not on PostgreSQL."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = settings.EMBEDDING_DIMENSION):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PgVector is not None:
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql" and PgVector is not None:
            return value
        import json
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value))
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql" and PgVector is not None:
            return value
        import json
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value


class TSVectorType(TypeDecorator):
    """Platform-independent TSVECTOR type that falls back to Text on non-Postgres engines."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_path: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    heading: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    
    # Vector embedding with configurable dimension
    embedding: Mapped[Any] = mapped_column(VectorType(settings.EMBEDDING_DIMENSION), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), default="stub")
    embedding_version: Mapped[str] = mapped_column(String(64), default="v1.0")

    # PostgreSQL full-text search vector
    tsv: Mapped[Any | None] = mapped_column(TSVectorType(), nullable=True)

    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_doc_index", "document_id", "chunk_index"),
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, running, completed, failed
    docs_scanned: Mapped[int] = mapped_column(Integer, default=0)
    docs_modified: Mapped[int] = mapped_column(Integer, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(32), default="hybrid")
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    refused: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
