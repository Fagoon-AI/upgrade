"""Redis-backed PubSub (FULL MODE).

One of the few approved backend modules permitted to import redis.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class RedisPubSub:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def publish(self, channel: str, message: str) -> int:
        try:
            return await self._redis.publish(channel, message)
        except Exception as e:
            log.error(f"Redis publish failed: {e}")
            return 0

    async def subscribe(
        self,
        channel: str,
        timeout: Optional[float] = None
    ) -> AsyncIterator[str]:
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(channel)
            log.debug(f"📡 Subscribed to: {channel}")

            while True:
                try:
                    # wait for a message with a timeout
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=timeout or 60.0
                    )

                    if message and message.get("type") == "message":
                        yield message["data"]

                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        except Exception as e:
            log.error(f"Subscription error on {channel}: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass
            log.debug(f"📡 Unsubscribed from: {channel}")

    async def health_check(self) -> dict:
        try:
            start = asyncio.get_event_loop().time()
            await self._redis.ping()
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            # Get info
            info = await self._redis.info("server")

            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
