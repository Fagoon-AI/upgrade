"""Runtime factory.

Reads LITE_MODE once and binds each interface to a concrete backend. This is
the single place where mode branching happens. Everything else in the app talks
to app.state.{limiter,queue,cache,redis} without knowing which mode is active.

This module and the *_limiter / *_cache / celery_queue backend modules are the
ONLY places permitted to import redis or celery (enforced by import-linter).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.core.settings import Settings
from src.services.cache.memory_cache import MemoryCache
from src.services.cache.redis_cache import RedisCache
from src.services.limiter.memory_limiter import MemoryRateLimiter
from src.services.limiter.redis_limiter import RedisRateLimiter
from src.services.taskqueue.celery_queue import CeleryTaskQueue
from src.services.taskqueue.inline_queue import InlineTaskQueue

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    limiter: Any
    queue: Any
    cache: Any
    redis: Any | None  # None in lite mode

    async def shutdown(self) -> None:
        if hasattr(self.queue, "shutdown"):
            await self.queue.shutdown()
        if self.redis is not None:
            await self.redis.aclose()


class InlineTaskQueueWithSyncSupport(InlineTaskQueue):
    """Extends InlineTaskQueue to seamlessly run blocking synchronous functions
    (such as Celery task wrappers) in worker threads using asyncio.to_thread,
    preventing event loop blockage and avoiding loop collision errors on nested loop runs."""

    async def _run(self, job_id, fn, *args, **kwargs) -> None:
        import asyncio
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn(*args, **kwargs)
            else:
                # Execute blocking synchronous function in a separate OS thread
                await asyncio.to_thread(fn, *args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception("inline job %s failed", job_id)


async def build_runtime(settings: Settings) -> Runtime:
    from src.core.task_processing.celery_tasks import (
        generate_video_task,
        process_webhook_message_task,
    )

    if settings.lite_mode:
        log.info("Building LITE runtime: in-memory limiter/cache, inline queue, no Redis.")
        queue = InlineTaskQueueWithSyncSupport()
        queue.register("generate_video_task", generate_video_task)
        queue.register("process_webhook_message_task", process_webhook_message_task)

        return Runtime(
            limiter=MemoryRateLimiter(),
            queue=queue,
            cache=MemoryCache(),
            redis=None,
        )

    log.info("Building FULL runtime: Redis limiter/cache, Celery queue.")
    import redis.asyncio as aioredis

    # Only pass ssl_cert_reqs if the URL implies an SSL connection (rediss://)
    kwargs = {"encoding": "utf-8", "decode_responses": True}
    if settings.REDIS_URL.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = "none"

    redis_client = aioredis.from_url(settings.REDIS_URL, **kwargs)

    from src.core.task_processing.celery_app import celery_app

    queue = CeleryTaskQueue(celery_app)
    queue.register("generate_video_task", generate_video_task)
    queue.register("process_webhook_message_task", process_webhook_message_task)

    return Runtime(
        limiter=RedisRateLimiter(redis_client),
        queue=queue,
        cache=RedisCache(redis_client),
        redis=redis_client,
    )
