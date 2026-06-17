"""Background task queue interface. Routes/services enqueue work through this;
the backend (Celery in full mode, asyncio inline in lite mode) is chosen at
startup. Job STATUS is always tracked in Postgres regardless of backend, so the
WebSocket status broadcaster is identical across modes."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskQueue(Protocol):
    def register(self, name: str, task: Any) -> None:
        """Register a task by name."""
        ...

    def enqueue(
        self, name: str, *args: Any, **kwargs: Any
    ) -> str:
        """Schedule registered task `name` to run in the background with `*args` and `**kwargs`.
        Returns an opaque job id immediately (does not await the work)."""
        ...
