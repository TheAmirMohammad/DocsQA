"""Tests for multi-format document parsers, git sources, weighted RRF, and reranking."""

from pathlib import Path

import pytest

from app.db.models import Chunk
from app.ingestion.git_source import sanitize_repo_name
from app.ingestion.parsers import (
    DocumentParserFactory,
    HTMLDocumentParser,
    RSTDocumentParser,
)
from app.retrieval.reranker import LexicalSemanticReranker
from app.retrieval.rrf import reciprocal_rank_fusion


def test_html_parser_extraction():
    """Verify HTML parser extracts headings, breadcrumbs, paragraphs, and preformatted code."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>FastAPI WebSockets</title></head>
    <body>
        <nav><a href="/">Home</a></nav>
        <h1>WebSockets in FastAPI</h1>
        <p>You can use WebSockets with FastAPI to handle real-time two-way communication.</p>
        <h2>Handling Connections</h2>
        <p>Accept websocket connections using the websocket decorator:</p>
        <pre><code>
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
        </code></pre>
        <footer>Footer boilerplate to ignore</footer>
    </body>
    </html>
    """
    parser = HTMLDocumentParser()
    title, chunks = parser.parse(html_content, fallback_title="Test")
    assert "WebSockets" in title
    assert len(chunks) >= 1
    # Check that code block was preserved and footer ignored
    combined_content = " ".join(c.content for c in chunks)
    assert "websocket.accept()" in combined_content
    assert "Footer boilerplate" not in combined_content


def test_rst_parser_extraction():
    """Verify reStructuredText parser parses section titles and code blocks."""
    rst_content = """
Deployment Guide
================

Overview
--------
Deploying FastAPI applications in production requires an ASGI server.

.. code-block:: bash

   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

.. note::
   Always use a reverse proxy like Nginx or Caddy in front of Uvicorn.
"""
    parser = RSTDocumentParser()
    title, chunks = parser.parse(rst_content, fallback_title="Deployment")
    assert title == "Deployment Guide"
    assert len(chunks) >= 1
    combined_content = " ".join(c.content for c in chunks)
    assert "uvicorn main:app" in combined_content
    assert "ASGI server" in combined_content


def test_document_parser_factory():
    """Verify factory routes by file suffix."""
    title_html, chunks_html = DocumentParserFactory.parse_file(
        Path("test.html"), "<h1>HTML Page</h1><p>Some content</p>"
    )
    assert "HTML Page" in title_html
    assert len(chunks_html) >= 1

    title_rst, chunks_rst = DocumentParserFactory.parse_file(
        Path("test.rst"), "RST Title\n=========\n\nBody text"
    )
    assert "RST Title" in title_rst
    assert len(chunks_rst) >= 1


def test_weighted_rrf_scoring():
    """Verify weighted RRF modifies scores according to channel multipliers."""
    vec_results = [("chunk_a", 0.9), ("chunk_b", 0.7)]
    fts_results = [("chunk_b", 5.0), ("chunk_a", 1.0)]

    # Standard unweighted (1.0 vs 1.0)
    unweighted = reciprocal_rank_fusion(vec_results, fts_results, k=60, top_n=2)
    assert len(unweighted) == 2

    # Heavy vector weight (2.0 vs 0.1) -> chunk_a should win decisively
    weighted = reciprocal_rank_fusion(
        vec_results, fts_results, k=60, top_n=2, weight_vector=2.0, weight_fts=0.1
    )
    assert weighted[0].chunk_id == "chunk_a"
    assert weighted[0].rrf_score > weighted[1].rrf_score


@pytest.mark.asyncio
async def test_lexical_semantic_reranker():
    """Verify reranker boosts chunk with exact heading match."""
    reranker = LexicalSemanticReranker()
    chunk1 = Chunk(
        id="c1",
        document_id="d1",
        chunk_index=0,
        heading="General FastAPI Concepts",
        content="FastAPI is a modern web framework for Python.",
        char_start=0,
        char_end=50,
        content_hash="h1",
    )
    chunk2 = Chunk(
        id="c2",
        document_id="d1",
        chunk_index=1,
        heading="OAuth2 Password and Bearer Tokens",
        content="OAuth2 Password flow uses bearer tokens for user authentication.",
        char_start=51,
        char_end=120,
        content_hash="h2",
    )

    # Initial ranking puts chunk1 first
    candidates = [
        (chunk1, 0.03, 1, 2),
        (chunk2, 0.02, 2, 1),
    ]

    reranked = await reranker.rerank(
        query="OAuth2 Password bearer tokens",
        candidates=candidates,
        top_k=2,
    )

    # chunk2 has exact match in heading and body, should be promoted to #1
    assert reranked[0][0].id == "c2"


def test_sanitize_repo_name():
    """Verify git URL sanitizer produces clean directory names."""
    assert sanitize_repo_name("https://github.com/tiangolo/fastapi.git") == "fastapi"
    assert sanitize_repo_name("git@github.com:encode/uvicorn.git") == "uvicorn"
    assert sanitize_repo_name("https://example.com/org/repo-docs_v2/") == "repo-docs_v2"
