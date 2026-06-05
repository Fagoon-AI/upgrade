from loguru import logger
from celery.signals import worker_shutdown, worker_init


@worker_init.connect
def initialize_worker_processes(**kwargs):
    """
    Celery worker process initialized.
    With per-task connection management, there's no global MongoDB client to 'connect' here.
    This signal can be used for other worker-wide initializations if needed.
    """
    logger.info("Celery worker process initialized. (This runs per worker process)")


@worker_shutdown.connect
def shutdown_worker_processes(**kwargs):
    """
    Called when a Celery worker process is shutting down.
    Allows for graceful cleanup of resources.
    """
    logger.info("Celery worker process shutting down. Performing graceful cleanup.")
    logger.info("Celery worker shutdown complete. MongoDB connections handled by individual tasks.")
