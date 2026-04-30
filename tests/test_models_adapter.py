"""Tests for model adapters and deterministic stub."""

import json
import math

import pytest

from app.models_adapter.stub import StubModelAdapter


@pytest.mark.asyncio
async def test_stub_embedding_dimension_and_norm():
    adapter = StubModelAdapter(dimension=128)
    texts = [
        "FastAPI is a modern, fast web framework.",
        "How do query parameters work?",
        "Security and OAuth2 authentication flow."
    ]
    embeddings = await adapter.embed(texts)
    assert len(embeddings) == 3

    for vec in embeddings:
        assert len(vec) == 128
        norm = math.sqrt(sum(x * x for x in vec))
        assert pytest.approx(norm, rel=1e-4) == 1.0


@pytest.mark.asyncio
async def test_stub_embedding_determinism():
    adapter = StubModelAdapter(dimension=128)
    text = "Deterministic testing is essential for CI pipelines."
    
    vec1 = (await adapter.embed([text]))[0]
    vec2 = (await adapter.embed([text]))[0]
    assert vec1 == vec2


@pytest.mark.asyncio
async def test_stub_generation_with_context():
    adapter = StubModelAdapter()
    context = (
        "[Chunk 1: /docs/security.md # OAuth2]\n"
        "OAuth2 password bearer flow uses OAuth2PasswordBearer class to extract bearer tokens from request headers."
    )
    prompt = "How does OAuth2PasswordBearer extract tokens?"
    answer = await adapter.generate(prompt=prompt, context=context)
    assert "OAuth2PasswordBearer" in answer
    assert "[1]" in answer or "[Chunk" in answer


@pytest.mark.asyncio
async def test_stub_refusal_on_empty_context():
    adapter = StubModelAdapter()
    answer = await adapter.generate(prompt="What is quantum gravity?", context="")
    assert "I do not have sufficient information in the documentation to answer this question." in answer


@pytest.mark.asyncio
async def test_ollama_adapter_prefixes_and_dimension_check(monkeypatch):
    import httpx

    from app.models_adapter import ollama_adapter

    sent: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        sent.append(texts)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0, 0.0] for _ in texts]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ollama_adapter.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setattr(ollama_adapter.settings, "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(ollama_adapter.settings, "EMBEDDING_DIMENSION", 3)

    adapter = ollama_adapter.OllamaModelAdapter()
    await adapter.embed(["doc text"])
    await adapter.embed_query("query text")
    assert sent == [["search_document: doc text"], ["search_query: query text"]]

    adapter.dimension = 768  # schema/model mismatch must fail loudly, not store bad vectors
    with pytest.raises(ValueError, match="768"):
        await adapter.embed(["doc text"])
