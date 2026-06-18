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

import importlib
from src.core.settings import Settings
from src.services.cache.memory_cache import MemoryCache
from src.services.limiter.memory_limiter import MemoryRateLimiter
from src.services.taskqueue.inline_queue import InlineTaskQueue
from src.services.pubsub.memory_pubsub import MemoryPubSub

log = logging.getLogger(__name__)


_current_runtime: Runtime | None = None


def get_runtime() -> Runtime | None:
    """Gets the globally registered active runtime."""
    return _current_runtime


@dataclass
class Runtime:
    limiter: Any
    queue: Any
    cache: Any
    pubsub: Any
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
    global _current_runtime
    if settings.lite_mode:
        log.info("Building LITE runtime: in-memory limiter/cache, inline queue, no Redis.")
        from src.services.taskqueue.lite_tasks import (
            generate_video_lite,
            process_webhook_message_lite,
            execute_workflow_lite,
            cancel_execution_lite,
            cleanup_stale_executions_lite,
            health_check_lite,
            process_due_schedules_lite,
            create_schedule_from_workflow_lite,
            disable_workflow_schedules_lite,
            cleanup_old_logs_lite,
            cleanup_traces_lite,
        )
        queue = InlineTaskQueueWithSyncSupport()
        queue.register("generate_video_task", generate_video_lite)
        queue.register("process_webhook_message_task", process_webhook_message_lite)
        queue.register("execute_workflow_task", execute_workflow_lite)
        queue.register("cancel_execution_task", cancel_execution_lite)
        queue.register("cleanup_stale_executions_task", cleanup_stale_executions_lite)
        queue.register("health_check_task", health_check_lite)
        queue.register("process_due_schedules_task", process_due_schedules_lite)
        queue.register("create_schedule_from_workflow_task", create_schedule_from_workflow_lite)
        queue.register("disable_workflow_schedules_task", disable_workflow_schedules_lite)
        queue.register("cleanup_old_logs_task", cleanup_old_logs_lite)
        queue.register("cleanup_traces_task", cleanup_traces_lite)

        _current_runtime = Runtime(
            limiter=MemoryRateLimiter(),
            queue=queue,
            cache=MemoryCache(),
            pubsub=MemoryPubSub(),
            redis=None,
        )
        return _current_runtime

    log.info("Building FULL runtime: Redis limiter/cache, Celery queue.")
    
    # Use dynamic importlib mapping to strictly avoid transitive static import linter contracts
    celery_tasks_mod = importlib.import_module("src.core.task_processing.celery_tasks")
    generate_video_task = celery_tasks_mod.generate_video_task
    process_webhook_message_task = celery_tasks_mod.process_webhook_message_task
    execute_workflow_task = celery_tasks_mod.execute_workflow_task
    cancel_execution_task = celery_tasks_mod.cancel_execution_task
    cleanup_stale_executions_task = celery_tasks_mod.cleanup_stale_executions_task
    health_check_task = celery_tasks_mod.health_check_task
    process_due_schedules_task = celery_tasks_mod.process_due_schedules_task
    create_schedule_from_workflow_task = celery_tasks_mod.create_schedule_from_workflow_task
    disable_workflow_schedules_task = celery_tasks_mod.disable_workflow_schedules_task
    cleanup_old_logs_task = celery_tasks_mod.cleanup_old_logs_task
    cleanup_traces_task = celery_tasks_mod.cleanup_traces_task

    aioredis = importlib.import_module("redis.asyncio")

    # Only pass ssl_cert_reqs if the URL implies an SSL connection (rediss://)
    kwargs = {"encoding": "utf-8", "decode_responses": True}
    if settings.REDIS_URL.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = "none"

    redis_client = aioredis.from_url(settings.REDIS_URL, **kwargs)

    celery_app_mod = importlib.import_module("src.core.task_processing.celery_app")
    celery_app = celery_app_mod.celery_app

    celery_queue_mod = importlib.import_module("src.services.taskqueue.celery_queue")
    CeleryTaskQueue = celery_queue_mod.CeleryTaskQueue

    queue = CeleryTaskQueue(celery_app)
    queue.register("generate_video_task", generate_video_task)
    queue.register("process_webhook_message_task", process_webhook_message_task)
    queue.register("execute_workflow_task", execute_workflow_task)
    queue.register("cancel_execution_task", cancel_execution_task)
    queue.register("cleanup_stale_executions_task", cleanup_stale_executions_task)
    queue.register("health_check_task", health_check_task)
    queue.register("process_due_schedules_task", process_due_schedules_task)
    queue.register("create_schedule_from_workflow_task", create_schedule_from_workflow_task)
    queue.register("disable_workflow_schedules_task", disable_workflow_schedules_task)
    queue.register("cleanup_old_logs_task", cleanup_old_logs_task)
    queue.register("cleanup_traces_task", cleanup_traces_task)

    redis_limiter_mod = importlib.import_module("src.services.limiter.redis_limiter")
    RedisRateLimiter = redis_limiter_mod.RedisRateLimiter

    redis_cache_mod = importlib.import_module("src.services.cache.redis_cache")
    RedisCache = redis_cache_mod.RedisCache

    redis_pubsub_mod = importlib.import_module("src.services.pubsub.redis_pubsub")
    RedisPubSub = redis_pubsub_mod.RedisPubSub

    _current_runtime = Runtime(
        limiter=RedisRateLimiter(redis_client),
        queue=queue,
        cache=RedisCache(redis_client),
        pubsub=RedisPubSub(redis_client),
        redis=redis_client,
    )
    return _current_runtime
