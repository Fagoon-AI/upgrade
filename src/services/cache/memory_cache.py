"""In-memory TTL cache (LITE MODE). Single-process only."""
from __future__ import annotations

import time
from typing import Any


class MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        expires_at = time.monotonic() + ttl_s if ttl_s else None
        self._store[key] = (expires_at, value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
