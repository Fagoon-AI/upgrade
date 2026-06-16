"""In-memory sliding-window rate limiter (LITE MODE).

Correct ONLY in a single process. Lite mode pins WEB_CONCURRENCY=1 and that
invariant is asserted at startup. With multiple workers, counts fragment.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_s
        q = self._hits[key]
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def sweep(self) -> int:
        """Drop empty keys to bound memory. Call periodically. Returns count removed."""
        empty = [k for k, q in self._hits.items() if not q]
        for k in empty:
            del self._hits[k]
        return len(empty)
