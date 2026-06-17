from celery import Celery
import ssl

from src.core.bootstrap import ensure_bootstrap
from src.core.settings import get_settings

# Guarantee that the Celery process runs the bootstrapper and loads persisted config.json values
ensure_bootstrap(get_settings())

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

if system_setting.CELERY_BROKER_URL.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={
            "ssl_cert_reqs": ssl.CERT_NONE
        }
    )

if system_setting.CELERY_RESULT_BACKEND.startswith("rediss://"):
    celery_app.conf.update(
        redis_backend_use_ssl={
            "ssl_cert_reqs": ssl.CERT_NONE
        }
    )