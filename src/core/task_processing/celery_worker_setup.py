import asyncio

from loguru import logger
from celery.signals import worker_shutdown, worker_init


@worker_init.connect
def initialize_worker_processes(**kwargs):
    """
    Celery worker process initialized.

    Builds the shared Runtime (Redis pubsub/cache/limiter) in this worker
    process so that `get_runtime()` resolves here too. Without this, workflow
    node execution running inside the worker publishes trace events against a
    `None` runtime and the frontend never receives live node progress, even
    though the graph itself executes correctly.
    """
    logger.info("Celery worker process initialized. (This runs per worker process)")

    from src.core.settings import get_settings
    from src.core.runtime import build_runtime

    try:
        asyncio.run(build_runtime(get_settings()))
        logger.info("Worker runtime (Redis pubsub/cache/limiter) initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize worker runtime: {e}", exc_info=True)


@worker_shutdown.connect
def shutdown_worker_processes(**kwargs):
    """
    Called when a Celery worker process is shutting down.
    Allows for graceful cleanup of resources.
    """
    logger.info("Celery worker process shutting down. Performing graceful cleanup.")

    from src.core.runtime import get_runtime

    rt = get_runtime()
    if rt is not None:
        try:
            asyncio.run(rt.shutdown())
        except Exception as e:
            logger.error(f"Error shutting down worker runtime: {e}", exc_info=True)

    logger.info("Celery worker shutdown complete. MongoDB connections handled by individual tasks.")
