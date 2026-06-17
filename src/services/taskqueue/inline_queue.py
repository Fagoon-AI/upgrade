"""Inline asyncio task queue (LITE MODE).

Runs the coroutine in the current event loop and returns a job id immediately.
Caveat: a job dies if the process restarts mid-run. Acceptable for a single
self-hosted user. Long video renders in lite mode therefore have no retry; the
DB row stays PROCESSING until the broadcaster/timeout marks it FAILED.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable

log = logging.getLogger(__name__)


class InlineTaskQueue:
    def __init__(self, task_registry: dict[str, Any] | None = None) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._registry = task_registry or {}

    def register(self, name: str, fn: Callable) -> None:
        self._registry[name] = fn

    def enqueue(
        self, name: str, *args: Any, **kwargs: Any
    ) -> str:
        fn = self._registry.get(name)
        if fn is None:
            raise KeyError(
                f"No task registered for '{name}'. "
                f"Register it via task_queue.register('{name}', the_task)."
            )
        job_id = str(uuid.uuid4())
        task = asyncio.create_task(self._run(job_id, fn, *args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def _run(self, job_id, fn, *args, **kwargs) -> None:
        try:
            await fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - log and swallow; status lives in DB
            log.exception("inline job %s failed", job_id)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
