# ADR-0002: ARQ over Celery for Asynchronous Ingestion Jobs

## Status
Accepted

## Context
Document ingestion involves crawling/reading markdown files, computing cryptographic hashes, parsing Markdown ASTs, invoking embedding adapters (which are async I/O network operations), and performing bulk database writes. Running ingestion synchronously in the HTTP request handler would cause HTTP timeouts on large repositories. Therefore, ingestion must run as an asynchronous background worker.

We evaluated task queue systems: **Celery** vs **ARQ** vs **FastAPI BackgroundTasks**.

## Decision Drivers
- **Asyncio Native:** FastAPI and asyncpg are asynchronous. Celery is fundamentally synchronous and running async tasks inside Celery requires hacky `asyncio.run()` wrappers within synchronous worker processes, causing event-loop lifecycle and connection-pool leakage issues.
- **Dependency footprint:** Celery pulls Kombu, billiard, vine, and complex broker configurations. ARQ has zero dependencies beyond Redis and asyncio.
- **Reliability over in-process background tasks:** FastAPI's built-in `BackgroundTasks` run within the web server process and are lost if the server container restarts or crashes mid-ingestion.

## Considered Options
1. **ARQ (Async Redis Queue) (Selected):**
   - *Pros:* 100% native Python `asyncio`, directly uses `redis.asyncio`, shares connection pools cleanly, lightweight, job status and result tracking built-in.
   - *Cons:* Python-only, Redis-only (which is already part of our stack for caching).
2. **Celery:**
   - *Pros:* Broad industry name recognition, supports RabbitMQ/Redis, extensive task routing.
   - *Cons:* Heavy, synchronous execution model conflicts with async SQLAlchemy and async HTTP clients, high memory footprint.
3. **FastAPI BackgroundTasks:**
   - *Pros:* Zero additional processes.
   - *Cons:* Non-durable, in-memory, ties worker CPU/IO to the web server process, no distributed horizontal scaling.

## Decision
We choose **ARQ with Redis** for asynchronous job queueing and background ingestion execution.

## Consequences
- The background worker runs alongside the API as a dedicated container in Docker Compose (`arq app.worker.tasks.WorkerSettings`).
- Shared database connection pooling is cleanly decoupled between API instances and workers.
- Job IDs returned by `POST /ingest` can be polled via `GET /jobs/{id}` for live progress.
