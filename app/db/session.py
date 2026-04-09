"""Database session management and lifecycle hooks."""

from collections.abc import AsyncGenerator
from datetime import UTC

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

# Engine configuration with pooling
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
    **({} if "sqlite" in settings.DATABASE_URL else {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
    })
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database schemas, extensions, and tables."""
    async with engine.begin() as conn:
        # If on PostgreSQL, ensure the pgvector extension is active
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            
        await conn.run_sync(Base.metadata.create_all)

        # Create indexes specifically for PostgreSQL if they don't exist
        if conn.dialect.name == "postgresql":
            # HNSW index for cosine distance
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
                ON chunks USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            # GIN index for full-text search
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chunks_tsv_gin 
                ON chunks USING gin (tsv);
            """))


async def get_or_create_index_version(session: AsyncSession) -> int:
    """Fetch current global index version, initializing to 1 if absent."""
    from datetime import datetime

    from sqlalchemy import select

    from app.db.models import SystemState

    # Select the column, not the entity: an identity-mapped row would hide a concurrent bump
    res = await session.execute(
        select(SystemState.value).where(SystemState.key == "index_version")
    )
    value = res.scalar_one_or_none()
    if value is None:
        new_state = SystemState(
            key="index_version",
            value="1",
            updated_at=datetime.now(UTC),
        )
        session.add(new_state)
        await session.commit()
        return 1
    return int(value)


async def bump_index_version(session: AsyncSession) -> int:
    """Atomically increment the global index version, orphaning every cached answer."""
    await get_or_create_index_version(session)
    await session.execute(text(
        "UPDATE system_state SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
        "WHERE key = 'index_version'"
    ))
    await session.commit()
    return await get_or_create_index_version(session)
