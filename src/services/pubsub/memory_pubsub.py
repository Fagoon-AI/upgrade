"""In-memory PubSub (LITE MODE).
Correct ONLY in a single process (WEB_CONCURRENCY=1 is enforced in lite mode).
"""
from __future__ import annotations
import asyncio
import logging
from typing import AsyncIterator, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class MemoryPubSub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, message: str) -> int:
        async with self._lock:
            queues = self._subscribers.get(channel, set())
            for q in queues:
                await q.put(message)
            return len(queues)

    async def subscribe(
        self,
        channel: str,
        timeout: Optional[float] = None
    ) -> AsyncIterator[str]:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = set()
            self._subscribers[channel].add(q)
        log.info(f"PUBSUB SUBSCRIBE: {channel}, total_subscribers={len(self._subscribers[channel])}")
        try:
            while True:
                try:
                    if timeout:
                        message = await asyncio.wait_for(q.get(), timeout=timeout)
                    else:
                        message = await q.get()
                    yield message
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
        finally:
            async with self._lock:
                if channel in self._subscribers:
                    self._subscribers[channel].discard(q)
                    if not self._subscribers[channel]:
                        del self._subscribers[channel]

    async def connect(self):
        """No-op compatibility with redis_manager API."""
        pass

    async def health_check(self) -> dict:
        return {
            "status": "healthy",
            "type": "in-memory",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
