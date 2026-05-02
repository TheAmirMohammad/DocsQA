"""Integration tests for FastAPI HTTP endpoints."""

import shutil

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.pipeline import IngestionPipeline


@pytest.mark.asyncio
async def test_healthz_endpoint(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data
    assert "index_version" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "docsqa_queries_total" in resp.text
    assert "docsqa_chunks_indexed_total" in resp.text


@pytest.mark.asyncio
async def test_ingest_and_documents_endpoint(client: AsyncClient, db_session: AsyncSession):
    # Ingest docs
    pipeline = IngestionPipeline(db_session)
    await pipeline.ingest_directory("./sample_docs/fastapi_tutorial")

    # List documents
    resp = await client.get("/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] >= 5
    assert data["total_chunks"] >= 10
    assert len(data["documents"]) >= 5


@pytest.mark.asyncio
async def test_ask_endpoint_and_cache(client: AsyncClient, db_session: AsyncSession):
    pipeline = IngestionPipeline(db_session)
    await pipeline.ingest_directory("./sample_docs/fastapi_tutorial")

    # 1. First query: Cache Miss
    resp1 = await client.post(
        "/ask",
        json={"question": "What is FastAPI built on?", "mode": "hybrid"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["cached"] is False
    assert not data1["refused"]
    assert len(data1["citations"]) > 0

    # 2. Second query: Cache Hit
    resp2 = await client.post(
        "/ask",
        json={"question": "What is FastAPI built on?", "mode": "hybrid"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["answer"] == data1["answer"]
    assert data2["latency_ms"] <= data1["latency_ms"] + 10.0  # cache latency is ultra fast


@pytest.mark.asyncio
async def test_ask_refusal_via_api(client: AsyncClient, db_session: AsyncSession):
    pipeline = IngestionPipeline(db_session)
    await pipeline.ingest_directory("./sample_docs/fastapi_tutorial")

    resp = await client.post(
        "/ask",
        json={"question": "How to calculate mortgage amortization schedules?", "mode": "hybrid"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is True
    assert "do not have sufficient information" in data["answer"].lower()


@pytest.mark.asyncio
async def test_reingest_invalidates_cached_answer(client: AsyncClient, db_session: AsyncSession, tmp_path):
    docs = tmp_path / "docs"
    shutil.copytree("./sample_docs/fastapi_tutorial", docs)
    pipeline = IngestionPipeline(db_session)
    await pipeline.ingest_directory(str(docs))

    question = {"question": "What is FastAPI built on?", "mode": "hybrid"}
    first = (await client.post("/ask", json=question)).json()
    assert (await client.post("/ask", json=question)).json()["cached"] is True

    # Change one document and re-ingest: the old cached answer must not be served
    intro = docs / "01_intro.md"
    intro.write_text(intro.read_text() + "\n\nFastAPI is also built on zebra-stripes.\n")
    await pipeline.ingest_directory(str(docs))

    after = (await client.post("/ask", json=question)).json()
    assert after["cached"] is False
    assert after["index_version"] > first["index_version"]


@pytest.mark.asyncio
async def test_ingest_rejects_paths_outside_docs_root(client: AsyncClient):
    for bad in ("/etc", "./sample_docs/../app", "./sample_docs/missing"):
        resp = await client.post("/ingest", json={"source_path": bad})
        assert resp.status_code == 400, bad


@pytest.mark.asyncio
async def test_cache_is_keyed_by_top_k(client: AsyncClient, db_session: AsyncSession):
    await IngestionPipeline(db_session).ingest_directory("./sample_docs/fastapi_tutorial")
    q = "What is FastAPI built on?"
    await client.post("/ask", json={"question": q, "top_k": 1})
    resp = (await client.post("/ask", json={"question": q, "top_k": 5})).json()
    assert resp["cached"] is False
