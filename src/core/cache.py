import asyncio
import json
import time
from typing import Any, Optional

from loguru import logger
from src.core.settings import system_setting

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None


class InMemoryCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        async with self._lock:
            expiry = time.time() + ex if ex else 0
            self._store[key] = (value, expiry)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            value, expiry = entry
            if expiry and expiry < time.time():
                del self._store[key]
                return None
            return value

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return (await self.get(key)) is not None


class RedisCache:
    def __init__(self, redis_url: str):
        if not aioredis:
            raise RuntimeError("redis.asyncio is required for RedisCache")
        self.client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self.client.set(key, value, ex=ex)

    async def get(self, key: str) -> Optional[Any]:
        value = await self.client.get(key)
        return value

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.client.exists(key) > 0


class CacheClient:
    def __init__(self, redis_url: Optional[str] = None):
        redis_url = redis_url or system_setting.REDIS_URL
        if redis_url and aioredis:
            try:
                self._backend = RedisCache(redis_url)
                logger.info("CacheClient initialized with Redis at {}", redis_url)
            except Exception as e:
                logger.warning("Failed to initialize Redis cache, falling back to in-memory cache: {}", e)
                self._backend = InMemoryCache()
        else:
            self._backend = InMemoryCache()
            logger.info("CacheClient initialized with in-memory fallback cache.")

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        await self._backend.set(key, value, ex=ex)

    async def get(self, key: str) -> Optional[Any]:
        value = await self._backend.get(key)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    async def delete(self, key: str) -> None:
        await self._backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(key)

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        await self.set(key, json.dumps(value), ex)

    async def get_json(self, key: str) -> Optional[Any]:
        return await self.get(key)
