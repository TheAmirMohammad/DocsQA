"""Initial database schema with pgvector and full-text search

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-02 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.config import settings

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Table: documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('source_path', sa.String(length=512), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('doc_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_documents_source_path', 'documents', ['source_path'], unique=True)
    op.create_index('ix_documents_content_hash', 'documents', ['content_hash'])

    # Table: chunks
    op.create_table(
        'chunks',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('document_id', sa.String(length=64), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('heading', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('source_url', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('embedding', Vector(settings.EMBEDDING_DIMENSION), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), server_default='stub', nullable=False),
        sa.Column('embedding_version', sa.String(length=64), server_default='v1.0', nullable=False),
        sa.Column('tsv', postgresql.TSVECTOR(), nullable=True),
        sa.Column('char_start', sa.Integer(), server_default='0', nullable=False),
        sa.Column('char_end', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_chunks_document_id', 'chunks', ['document_id'])
    op.create_index('ix_chunks_content_hash', 'chunks', ['content_hash'])
    op.create_index('ix_chunks_doc_index', 'chunks', ['document_id', 'chunk_index'])
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tsv_gin ON chunks USING gin (tsv);")

    # Table: ingestion_jobs
    op.create_table(
        'ingestion_jobs',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('source_path', sa.String(length=512), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('docs_scanned', sa.Integer(), server_default='0', nullable=False),
        sa.Column('docs_modified', sa.Integer(), server_default='0', nullable=False),
        sa.Column('chunks_created', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Table: query_logs
    op.create_table(
        'query_logs',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('retrieval_mode', sa.String(length=32), server_default='hybrid', nullable=False),
        sa.Column('top_score', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('refused', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('cache_hit', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('latency_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Table: system_state
    op.create_table(
        'system_state',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('system_state')
    op.drop_table('query_logs')
    op.drop_table('ingestion_jobs')
    op.drop_table('chunks')
    op.drop_table('documents')
