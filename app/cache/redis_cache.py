"""Redis response cache with normalized query hashing and O(1) index-version invalidation."""

import json
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.ingestion.hasher import compute_cache_key


class QuestionCache:
    """
    Semantic response cache keyed on:
      docsqa:cache:v{index_version}:{mode}:{hash(normalized_query)}
      
    index_version lives in PostgreSQL (system_state) and is bumped by every ingestion
    that changes the index, so old entries simply stop being addressed (TTL reaps them)
    without blocking Redis with SCAN/FLUSH.
    """

    def __init__(self, redis_url: str = settings.REDIS_URL):
        self.redis_url = redis_url
        self._client: redis.Redis | None = None
        self._memory_fallback: dict[str, str] = {}

    async def get_client(self) -> redis.Redis | None:
        if self._client is None:
            try:
                self._client = redis.from_url(self.redis_url, decode_responses=True)
                await self._client.ping()
            except Exception:
                # Fallback to local in-memory dict if Redis is unavailable in current test environment
                self._client = None
        return self._client

    async def get(self, query: str, mode: str, index_version: int) -> dict[str, Any] | None:
        cache_key = compute_cache_key(index_version, mode, query)

        client = await self.get_client()
        if client:
            try:
                val = await client.get(cache_key)
                if val:
                    return json.loads(val)
            except Exception:
                pass
        else:
            val = self._memory_fallback.get(cache_key)
            if val:
                return json.loads(val)

        return None

    async def set(
        self,
        query: str,
        mode: str,
        index_version: int,
        data: dict[str, Any],
        ttl: int = settings.CACHE_TTL_SECONDS,
    ) -> None:
        cache_key = compute_cache_key(index_version, mode, query)
        payload = json.dumps(data)

        client = await self.get_client()
        if client:
            try:
                await client.set(cache_key, payload, ex=ttl)
                return
            except Exception:
                pass
        self._memory_fallback[cache_key] = payload

    async def clear(self) -> None:
        self._memory_fallback.clear()
        client = await self.get_client()
        if client:
            try:
                keys = await client.keys("docsqa:*")
                if keys:
                    await client.delete(*keys)
            except Exception:
                pass

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


cache_instance = QuestionCache()
