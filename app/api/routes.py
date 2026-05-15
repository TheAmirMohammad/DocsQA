"""FastAPI API routes implementation for DocsQA."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AskRequest,
    AskResponse,
    CitationSchema,
    DocumentItemSchema,
    DocumentsResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    JobStatusResponse,
    RetrievedChunkDebugSchema,
)
from app.cache.redis_cache import cache_instance
from app.config import settings
from app.db.models import Chunk, Document, IngestionJob, QueryLog
from app.db.session import (
    AsyncSessionLocal,
    get_db_session,
    get_or_create_index_version,
)
from app.ingestion.pipeline import IngestionPipeline
from app.observability.logging import logger
from app.observability.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    CHUNKS_INDEXED_TOTAL,
    INGESTION_JOBS_TOTAL,
    QUERIES_TOTAL,
    QUERY_LATENCY,
    REFUSALS_TOTAL,
)
from app.retrieval.engine import RetrievalEngine

router = APIRouter()


@router.post("/ask", response_model=AskResponse, summary="Ask a question against documentation")
async def ask_question(
    payload: AskRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AskResponse:
    """
    Answers questions using hybrid retrieval (pgvector + full-text search) merged with RRF.
    Answers include inline citations. When retrieved evidence is weak, the API refuses instead of hallucinating.
    """
    start_time = time.perf_counter()
    index_version = await get_or_create_index_version(session)
    cache_variant = f"{payload.mode}:top{payload.top_k}:rerank{payload.rerank}"

    # 1. Semantic Cache check
    if not payload.bypass_cache:
        cached_data = await cache_instance.get(payload.question, cache_variant, index_version)
        if cached_data:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            CACHE_HITS_TOTAL.inc()
            QUERIES_TOTAL.labels(mode=payload.mode, status="success", cached="true").inc()
            QUERY_LATENCY.labels(mode=payload.mode, cached="true").observe(latency_ms / 1000.0)

            return AskResponse(
                answer=cached_data["answer"],
                citations=[CitationSchema(**c) for c in cached_data.get("citations", [])],
                refused=cached_data.get("refused", False),
                cached=True,
                index_version=index_version,
                latency_ms=latency_ms,
                retrieval_mode=payload.mode,
                debug=cached_data.get("debug"),
            )

    CACHE_MISSES_TOTAL.inc()

    # 2. Retrieval & Generation
    engine = RetrievalEngine(session)
    retrieval_res = await engine.query(
        query_text=payload.question,
        mode=payload.mode,
        top_k=payload.top_k,
        rerank=payload.rerank,
    )

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    elapsed_sec = latency_ms / 1000.0

    if retrieval_res.refused:
        REFUSALS_TOTAL.inc()
        QUERIES_TOTAL.labels(mode=payload.mode, status="refused", cached="false").inc()
    else:
        QUERIES_TOTAL.labels(mode=payload.mode, status="success", cached="false").inc()

    QUERY_LATENCY.labels(mode=payload.mode, cached="false").observe(elapsed_sec)

    citations_data = [
        CitationSchema(
            index=c.index,
            source_url=c.source_url,
            heading=c.heading,
            chunk_id=c.chunk_id,
        )
        for c in retrieval_res.citations
    ]

    debug_info = {
        "top_score": retrieval_res.top_score,
        "retrieved_chunks": [
            RetrievedChunkDebugSchema(
                chunk_id=rc.chunk_id,
                heading=rc.heading,
                source_url=rc.source_url,
                content_preview=rc.content,
                score=rc.score,
                vector_rank=rc.vector_rank,
                fts_rank=rc.fts_rank,
            ).model_dump()
            for rc in retrieval_res.retrieved_chunks
        ],
    }

    # 3. Store in Semantic Cache
    if not payload.bypass_cache:
        await cache_instance.set(
            payload.question,
            cache_variant,
            index_version,
            {
                "answer": retrieval_res.answer,
                "citations": [c.model_dump() for c in citations_data],
                "refused": retrieval_res.refused,
                "debug": debug_info,
            },
        )

    # 4. Async Query Log entry
    try:
        log_entry = QueryLog(
            query_text=payload.question,
            retrieval_mode=payload.mode,
            top_score=retrieval_res.top_score,
            refused=retrieval_res.refused,
            cache_hit=False,
            latency_ms=latency_ms,
        )
        session.add(log_entry)
        await session.commit()
    except Exception as e:
        logger.warning("Failed to save query log", error=str(e))

    return AskResponse(
        answer=retrieval_res.answer,
        citations=citations_data,
        refused=retrieval_res.refused,
        cached=False,
        index_version=index_version,
        latency_ms=latency_ms,
        retrieval_mode=payload.mode,
        debug=debug_info,
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Trigger incremental ingestion",
    responses={400: {"description": "source_path is not a directory under DOCS_ROOT"}},
)
async def trigger_ingestion(
    payload: IngestRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> IngestResponse:
    """Queue or run incremental documentation ingestion with content-hash checks."""
    if payload.git_url:
        from app.ingestion.git_source import sanitize_repo_name
        repo_name = sanitize_repo_name(payload.git_url)
        git_target = Path(settings.DOCS_ROOT) / "git_repos" / repo_name
        source_dir = str(git_target / payload.subpath if payload.subpath else git_target)
        display_path = f"git:{payload.git_url}@{payload.branch}"
    else:
        source_dir = payload.source_path or settings.SAMPLE_DOCS_PATH
        # Trust boundary: never let a request read arbitrary server directories
        try:
            resolved = Path(source_dir).resolve()
            allowed = resolved.is_relative_to(Path(settings.DOCS_ROOT).resolve()) and resolved.is_dir()
        except (ValueError, OSError):
            allowed = False
        if not allowed:
            raise HTTPException(status_code=400, detail="source_path must be a directory under DOCS_ROOT")
        source_dir = str(resolved)  # hand the checked absolute path to the worker, not the raw input
        display_path = source_dir

    job_id = str(uuid.uuid4())
    job = IngestionJob(
        id=job_id,
        source_path=display_path,
        status="pending",
    )
    session.add(job)
    await session.commit()

    # Try enqueuing with ARQ Redis worker if available
    enqueued = False
    try:
        from arq.connections import RedisSettings, create_pool
        redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis_pool.enqueue_job(
            "ingest_documentation_job",
            source_path=source_dir,
            job_id=job_id,
            _job_id=job_id,
        )
        await redis_pool.close()
        enqueued = True
        logger.info("Ingestion job enqueued via ARQ Redis worker", job_id=job_id)
    except Exception:
        enqueued = False

    if not enqueued:
        # Fallback to FastAPI BackgroundTasks for local/standalone execution
        async def run_inline():
            async with AsyncSessionLocal() as bg_session:
                pipeline = IngestionPipeline(bg_session)
                try:
                    if payload.git_url:
                        await pipeline.ingest_git_repository(
                            git_url=payload.git_url,
                            branch=payload.branch,
                            subpath=payload.subpath,
                            job_id=job_id,
                        )
                    else:
                        await pipeline.ingest_directory(source_dir, job_id=job_id)
                    INGESTION_JOBS_TOTAL.labels(status="completed").inc()
                    # Update gauge
                    count_res = await bg_session.execute(select(func.count(Chunk.id)))
                    CHUNKS_INDEXED_TOTAL.set(count_res.scalar() or 0)
                except Exception:
                    INGESTION_JOBS_TOTAL.labels(status="failed").inc()

        background_tasks.add_task(run_inline)
        logger.info("Ingestion job started via background task", job_id=job_id)

    return IngestResponse(
        job_id=job_id,
        status="pending",
        message=f"Ingestion job for '{display_path}' registered.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="Get ingestion job status")
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JobStatusResponse:
    """Retrieve status, statistics, and errors for a specific ingestion job."""
    res = await session.execute(
        select(IngestionJob).where(IngestionJob.id == job_id)
    )
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        id=job.id,
        source_path=job.source_path,
        status=job.status,
        docs_scanned=job.docs_scanned,
        docs_modified=job.docs_modified,
        chunks_created=job.chunks_created,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get("/documents", response_model=DocumentsResponse, summary="List indexed documentation files")
async def list_documents(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentsResponse:
    """List all documents currently in the index along with chunk counts and content hashes."""
    stmt = (
        select(
            Document.id,
            Document.source_path,
            Document.title,
            Document.content_hash,
            Document.updated_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Document.id == Chunk.document_id)
        .group_by(Document.id)
        .order_by(Document.source_path)
    )
    res = await session.execute(stmt)
    rows = res.all()

    total_chunks = sum(r.chunk_count for r in rows)
    CHUNKS_INDEXED_TOTAL.set(total_chunks)

    items = [
        DocumentItemSchema(
            id=r.id,
            source_path=r.source_path,
            title=r.title,
            content_hash=r.content_hash,
            chunks_count=r.chunk_count,
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in rows
    ]

    return DocumentsResponse(
        total_documents=len(items),
        total_chunks=total_chunks,
        documents=items,
    )


@router.get("/evals/latest", summary="Get most recent evaluation harness report")
async def get_latest_evals() -> dict[str, Any]:
    """Returns the latest evaluation report comparing Vector, FTS, and Hybrid RRF."""
    json_path = Path("evals/latest_report.json")
    md_path = Path("evals/latest_report.md")

    report_data = {}
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

    markdown_summary = ""
    if md_path.exists():
        with open(md_path, "r", encoding="utf-8") as f:
            markdown_summary = f.read()

    if not report_data and not markdown_summary:
        return {
            "status": "not_run",
            "message": "Evaluation suite has not been executed yet. Run 'uv run python scripts/run_evals.py' to generate.",
        }

    return {
        "status": "ready",
        "data": report_data,
        "markdown": markdown_summary,
    }


@router.get("/healthz", response_model=HealthResponse, summary="Service health check")
async def health_check(
    session: AsyncSession = Depends(get_db_session),
) -> HealthResponse:
    """Probe PostgreSQL, Redis, and global index version."""
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1;"))
    except Exception as e:
        db_status = f"unhealthy: {e!s}"

    redis_status = "ok"
    try:
        client = await cache_instance.get_client()
        if client:
            await client.ping()
        else:
            redis_status = "standalone_memory_fallback"
    except Exception as e:
        redis_status = f"unreachable: {e!s}"

    index_ver = 1
    try:
        index_ver = await get_or_create_index_version(session)
    except Exception:
        pass

    overall = "ok" if "unhealthy" not in db_status and "unreachable" not in redis_status else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
        index_version=index_ver,
        environment=settings.ENVIRONMENT,
    )


@router.get("/metrics", summary="Prometheus metrics scrape endpoint")
async def prometheus_metrics() -> Response:
    """Export Prometheus format metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
