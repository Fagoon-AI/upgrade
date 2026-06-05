from celery import Celery

from src.core.settings import system_setting


celery_app = Celery(
    "src.core.task_processing",
    broker=system_setting.CELERY_BROKER_URL,
    backend=system_setting.CELERY_RESULT_BACKEND,
    include=["src.core.task_processing.celery_tasks", "src.core.task_processing.celery_worker_setup"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)