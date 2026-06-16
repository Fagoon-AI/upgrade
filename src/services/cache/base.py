"""Cache / ephemeral key-value interface. Redis in full mode, in-process dict
with TTL in lite mode."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
