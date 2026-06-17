"""Redis-backed cache (FULL MODE). One of the few modules allowed to import
redis. Values are JSON-encoded so any JSON-serializable payload round-trips."""
from __future__ import annotations

import json
from typing import Any


class RedisCache:
    def __init__(self, redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(f"cache:{key}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw

    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        raw = json.dumps(value)
        if ttl_s:
            await self._redis.set(f"cache:{key}", raw, ex=ttl_s)
        else:
            await self._redis.set(f"cache:{key}", raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(f"cache:{key}")
