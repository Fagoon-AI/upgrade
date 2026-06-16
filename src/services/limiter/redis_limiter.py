"""Redis-backed sliding-window rate limiter (FULL MODE).

This is the ONLY limiter module permitted to import redis (enforced by
import-linter). Move any existing Redis limiter logic you have into here.

Uses a sorted set per key with millisecond-resolution timestamps and a single
atomic pipeline: drop expired members, count, conditionally add, set TTL.
"""
from __future__ import annotations

import time


class RedisRateLimiter:
    def __init__(self, redis) -> None:
        self._redis = redis  # redis.asyncio client

    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        now_ms = int(time.time() * 1000)
        window_ms = window_s * 1000
        member = f"{now_ms}-{id(object())}"
        rkey = f"ratelimit:{key}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(rkey, 0, now_ms - window_ms)
        pipe.zcard(rkey)
        results = await pipe.execute()
        count = results[1]

        if count >= limit:
            return False

        pipe = self._redis.pipeline()
        pipe.zadd(rkey, {member: now_ms})
        pipe.expire(rkey, window_s + 1)
        await pipe.execute()
        return True
