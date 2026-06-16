"""Rate limiter interface. Business code depends only on this Protocol;
the concrete backend is chosen once at startup by src.core.runtime."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        """Return True if this hit is within `limit` per rolling `window_s`
        seconds for `key`, and record it. Return False to reject."""
        ...
