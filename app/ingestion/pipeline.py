"""Incremental ingestion pipeline with content-hash tracking and AST chunking."""

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk, Document, IngestionJob
from app.db.session import bump_index_version
from app.ingestion.chunker import MarkdownChunker
from app.ingestion.git_source import clone_git_repository
from app.ingestion.hasher import compute_sha256
from app.ingestion.parsers import DocumentParserFactory
from app.models_adapter import get_model_adapter

SUPPORTED_EXTENSIONS = (".md", ".markdown", ".rst", ".rest", ".html", ".htm")


class IngestionPipeline:
    """
    Ingests documentation directories into PostgreSQL with pgvector and full-text search.
    Implements incremental hashing to avoid re-embedding unchanged documents.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.chunker = MarkdownChunker(max_words=settings.CHUNK_MAX_WORDS)
        self.adapter = get_model_adapter()

    async def ingest_directory(
        self,
        docs_dir: str,
        job_id: str | None = None,
    ) -> IngestionJob:
        """Process a directory of documentation files incrementally."""
        target_path = Path(docs_dir).resolve()
        if not target_path.exists() or not target_path.is_dir():
            raise ValueError(f"Directory not found: {docs_dir}")
        # source_path = path relative to DOCS_ROOT, so every source has a unique, stable identity
        # (two dirs named "guide", or re-ingesting the root itself, never collide or duplicate)
        docs_root = Path(settings.DOCS_ROOT).resolve()
        base = docs_root if target_path.is_relative_to(docs_root) else target_path.parent
        source_prefix = target_path.relative_to(base).as_posix()
        prefix = "" if source_prefix == "." else f"{source_prefix}/"

        job = None
        if job_id:
            job_res = await self.session.execute(
                select(IngestionJob).where(IngestionJob.id == job_id)
            )
            job = job_res.scalar_one_or_none()

        if not job:
            import uuid
            job = IngestionJob(
                id=job_id or str(uuid.uuid4()),
                source_path=str(target_path),
                status="running",
                docs_scanned=0,
                docs_modified=0,
                chunks_created=0,
            )
            self.session.add(job)
            await self.session.commit()
        else:
            job.status = "running"
            await self.session.commit()

        index_changed = False  # set once any file's new chunks are committed
        try:
            # 1. Discover all documentation files (Markdown, reST, HTML)
            discovered_files: list[Path] = []
            for root, _, files in os.walk(target_path):
                for name in files:
                    if name.endswith(SUPPORTED_EXTENSIONS):
                        discovered_files.append(Path(root) / name)
            discovered_files.sort()

            job.docs_scanned = len(discovered_files)
            docs_modified = 0
            total_new_chunks = 0
            seen_source_paths = set()

            # 2. Process each file incrementally
            for file_path in discovered_files:
                if file_path.is_symlink():
                    continue  # never follow links out of the docs tree
                rel_path = file_path.relative_to(base).as_posix()
                seen_source_paths.add(rel_path)

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                file_hash = compute_sha256(content)
                title, chunks = DocumentParserFactory.parse_file(file_path, content)

                # Check if document already exists
                stmt = select(Document).where(Document.source_path == rel_path)
                doc_res = await self.session.execute(stmt)
                existing_doc = doc_res.scalar_one_or_none()

                if (
                    existing_doc
                    and existing_doc.content_hash == file_hash
                    and not await self._has_stale_embeddings(existing_doc.id)
                ):
                    # Unchanged text embedded by the current model: skip re-embedding
                    continue

                # Document is either brand new or modified
                docs_modified += 1

                # Generate embeddings in batch
                chunk_texts = [c.content for c in chunks]
                embeddings = await self.adapter.embed(chunk_texts) if chunk_texts else []

                if existing_doc:
                    # Clear old chunks
                    await self.session.execute(
                        delete(Chunk).where(Chunk.document_id == existing_doc.id)
                    )
                    existing_doc.title = title
                    existing_doc.content_hash = file_hash
                    existing_doc.updated_at = datetime.now(UTC)
                    doc_id = existing_doc.id
                else:
                    new_doc = Document(
                        source_path=rel_path,
                        title=title,
                        content_hash=file_hash,
                        doc_metadata={"file_name": file_path.name, "abs_path": str(file_path)},
                    )
                    self.session.add(new_doc)
                    await self.session.flush()
                    doc_id = new_doc.id

                # Insert new chunks
                for draft, emb in zip(chunks, embeddings):
                    chunk_row = Chunk(
                        document_id=doc_id,
                        chunk_index=draft.chunk_index,
                        content=draft.content,
                        content_hash=draft.content_hash,
                        heading=draft.heading,
                        source_url=f"{rel_path}#{self._slugify(draft.heading)}",
                        embedding=emb,
                        embedding_model=self.adapter.model_name,
                        embedding_version=self.adapter.model_version,
                        char_start=draft.char_start,
                        char_end=draft.char_end,
                    )
                    self.session.add(chunk_row)
                    total_new_chunks += 1

                await self.session.commit()
                index_changed = True

            # 3. Handle pruned/deleted files (only within this source)
            all_docs_stmt = select(Document).where(Document.source_path.startswith(prefix, autoescape=True))
            all_docs_res = await self.session.execute(all_docs_stmt)
            for db_doc in all_docs_res.scalars().all():
                if db_doc.source_path not in seen_source_paths:
                    await self.session.delete(db_doc)
                    docs_modified += 1

            # 4. If changes occurred, index new text for FTS and bump index version (commits prunes too)
            if docs_modified > 0:
                await self._publish_index_changes()

            job.docs_modified = docs_modified
            job.chunks_created = total_new_chunks
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            await self.session.commit()
            return job

        except BaseException as e:  # incl. CancelledError from an ARQ job timeout
            await self.session.rollback()
            if index_changed:
                # Files committed before the failure are live: make them searchable and
                # orphan cached answers, or stale answers would survive until the cache TTL
                await self._publish_index_changes()
            job.status = "failed"
            job.error_message = str(e) or type(e).__name__
            job.completed_at = datetime.now(UTC)
            await self.session.commit()
            raise

    async def _publish_index_changes(self) -> None:
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            await self.session.execute(
                text("UPDATE chunks SET tsv = to_tsvector('english', content) WHERE tsv IS NULL;")
            )
        await bump_index_version(self.session)

    async def _has_stale_embeddings(self, document_id: str) -> bool:
        """True if any chunk was embedded by a different model/version than the active adapter."""
        res = await self.session.execute(
            select(Chunk.id)
            .where(
                Chunk.document_id == document_id,
                or_(
                    Chunk.embedding_model != self.adapter.model_name,
                    Chunk.embedding_version != self.adapter.model_version,
                ),
            )
            .limit(1)
        )
        return res.first() is not None

    async def ingest_git_repository(
        self,
        git_url: str,
        branch: str = "main",
        subpath: str | None = None,
        job_id: str | None = None,
    ) -> IngestionJob:
        """Clones a remote git repository and ingests documentation files."""
        cloned_dir = clone_git_repository(git_url, branch=branch)
        target_dir = cloned_dir / subpath if subpath else cloned_dir
        return await self.ingest_directory(str(target_dir), job_id=job_id)

    def _extract_title(self, content: str, fallback: str) -> str:
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                return line_s.lstrip("# ").strip()
        return fallback.replace("_", " ").title()

    def _slugify(self, text: str) -> str:
        import re
        s = re.sub(r"[^\w\s-]", "", text.lower())
        return re.sub(r"[-\s]+", "-", s).strip("-")
