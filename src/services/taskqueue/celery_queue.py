"""Celery-backed task queue (FULL MODE).

The ONLY taskqueue module permitted to import celery (enforced by import-linter).

Because Celery serializes tasks by name (not arbitrary coroutines), register
your real jobs as Celery tasks elsewhere (e.g. generate_video_task) and map the
callable passed to enqueue() onto the matching registered task. The simplest
robust pattern is a name registry: pass a registered task, or look it up by
fn.__name__. Adapt to your existing celery_app task definitions.
"""
from __future__ import annotations

from typing import Any


class CeleryTaskQueue:
    def __init__(self, celery_app, task_registry: dict[str, Any] | None = None) -> None:
        self._celery = celery_app
        # maps a plain function name -> registered celery task (.delay-able)
        self._registry = task_registry or {}

    def register(self, name: str, celery_task) -> None:
        self._registry[name] = celery_task

    def enqueue(
        self, name: str, *args: Any, **kwargs: Any
    ) -> str:
        task = self._registry.get(name)
        if task is None:
            raise KeyError(
                f"No Celery task registered for '{name}'. "
                f"Register it via CeleryTaskQueue.register('{name}', the_task)."
            )
        async_result = task.delay(*args, **kwargs)
        return async_result.id
