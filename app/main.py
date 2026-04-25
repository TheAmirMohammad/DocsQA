"""Main FastAPI application entry point for DocsQA."""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.cache.redis_cache import cache_instance
from app.config import settings
from app.db.session import engine, init_db
from app.observability.logging import logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown procedures."""
    setup_logging()
    logger.info(
        "DocsQA service starting up",
        environment=settings.ENVIRONMENT,
        model_provider=settings.MODEL_PROVIDER,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
    )
    # Initialize database schemas / extensions
    try:
        await init_db()
        logger.info("Database schemas and pgvector extensions verified.")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))

    yield

    logger.info("DocsQA service shutting down")
    await cache_instance.close()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=(
        "Production-grade question-answering API over technical documentation featuring "
        "hybrid retrieval (pgvector + full-text search with Reciprocal Rank Fusion), "
        "semantic Redis caching with index-version invalidation, answer refusal, and "
        "automated regression evaluation harness."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log HTTP requests with correlation IDs and calculate request duration."""
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(request_id=req_id)

    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = req_id
        
        # Avoid logging noisy prometheus scrape endpoint every few seconds
        if request.url.path not in ("/metrics", "/healthz"):
            logger.info(
                "HTTP request handled",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        return response
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            "Unhandled exception in request",
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error occurred.", "request_id": req_id},
            headers={"X-Request-ID": req_id},
        )
    finally:
        structlog.contextvars.clear_contextvars()


app.include_router(router)
