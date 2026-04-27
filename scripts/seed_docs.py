"""Seed sample documentation into DocsQA database."""

import asyncio

from app.config import settings
from app.db.session import AsyncSessionLocal, init_db
from app.ingestion.pipeline import IngestionPipeline


async def seed():
    print(f"Initializing database and indexing docs from: {settings.SAMPLE_DOCS_PATH}")
    await init_db()
    async with AsyncSessionLocal() as session:
        pipeline = IngestionPipeline(session)
        job = await pipeline.ingest_directory(settings.SAMPLE_DOCS_PATH)
        print(f"✅ Ingestion completed! Scanned: {job.docs_scanned}, Modified: {job.docs_modified}, Chunks created: {job.chunks_created}")

if __name__ == "__main__":
    asyncio.run(seed())
