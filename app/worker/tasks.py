"""ARQ asynchronous worker settings and background ingestion tasks."""

from typing import Any

from arq.connections import RedisSettings

from app.config import settings
from app.db.session import AsyncSessionLocal, init_db
from app.ingestion.pipeline import IngestionPipeline


async def ingest_documentation_job(ctx: dict[str, Any], source_path: str, job_id: str) -> dict[str, Any]:
    """Background task executed by ARQ worker to ingest a documentation directory."""
    async with AsyncSessionLocal() as session:
        pipeline = IngestionPipeline(session)
        job = await pipeline.ingest_directory(docs_dir=source_path, job_id=job_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "docs_scanned": job.docs_scanned,
            "docs_modified": job.docs_modified,
            "chunks_created": job.chunks_created,
        }


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook: ensure tables and extensions are present."""
    await init_db()


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""


class WorkerSettings:
    """ARQ Worker configuration."""
    functions = [ingest_documentation_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = 1800  # large doc sets embed slowly on real models
    max_jobs = 1  # serialize ingestion: concurrent runs race on documents.source_path
    poll_delay = 0.5
