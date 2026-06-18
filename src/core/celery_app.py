from celery import Celery, signals
from celery.schedules import crontab
from kombu import Exchange, Queue
from loguru import logger

from src.core.config import settings


# ============================================================
# QUEUE CONFIGURATION
# ============================================================

# Define exchanges
default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("priority", type="direct")

# Define queues
task_queues = (
    # Default queue for normal tasks
    Queue(
        "default",
        exchange=default_exchange,
        routing_key="default",
        queue_arguments={"x-max-priority": 10}
    ),
    # High priority queue for critical tasks
    Queue(
        "high_priority",
        exchange=priority_exchange,
        routing_key="high",
        queue_arguments={"x-max-priority": 10}
    ),
    # Low priority queue for background tasks
    Queue(
        "low_priority",
        exchange=default_exchange,
        routing_key="low",
        queue_arguments={"x-max-priority": 5}
    ),
    # Scheduled tasks queue
    Queue(
        "scheduled",
        exchange=default_exchange,
        routing_key="scheduled"
    ),
)

# Task routing
task_routes = {
    # Workflow execution - default priority
    "execute_workflow_task": {"queue": "default", "routing_key": "default"},
    "app.tasks.workflow.execute_workflow_task": {"queue": "default", "routing_key": "default"},

    # Cleanup tasks - low priority
    "cleanup_old_logs_task": {"queue": "low_priority", "routing_key": "low"},
    "app.tasks.cleanup.cleanup_old_logs_task": {"queue": "low_priority", "routing_key": "low"},
    "cleanup_stale_executions_task": {"queue": "low_priority", "routing_key": "low"},

    # Cancel/health tasks - high priority
    "cancel_execution_task": {"queue": "high_priority", "routing_key": "high"},
    "health_check_task": {"queue": "high_priority", "routing_key": "high"},

    # Scheduler tasks
    "process_due_schedules_task": {"queue": "scheduled", "routing_key": "scheduled"},
    "create_schedule_from_workflow_task": {"queue": "default", "routing_key": "default"},
    "disable_workflow_schedules_task": {"queue": "default", "routing_key": "default"},
}


# ============================================================
# CELERY APPLICATION
# ============================================================

celery_app = Celery(
    "workflow_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.workflow",
        "app.tasks.cleanup",
        "app.tasks.scheduler",
    ]
)


# ============================================================
# CONFIGURATION
# ============================================================

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,

    # Result backend
    result_expires=86400,  # 24 hours
    result_extended=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,

    # Worker configuration
    worker_prefetch_multiplier=1,  # Disable prefetching for fairness
    worker_max_tasks_per_child=1000,  # Recycle workers
    worker_max_memory_per_child=512000,  # 512MB memory limit
    worker_disable_rate_limits=False,

    # Concurrency
    worker_concurrency=4,  # Adjust based on resources

    # Task time limits (can be overridden per-task)
    task_soft_time_limit=3600,  # 1 hour soft limit
    task_time_limit=3900,  # 1h 5min hard limit

    # Retry policy defaults
    task_default_retry_delay=60,
    task_max_retries=3,

    # Queue configuration
    task_queues=task_queues,
    task_routes=task_routes,
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # Rate limiting
    task_annotations={
        "execute_workflow_task": {
            "rate_limit": "100/m",  # 100 per minute per worker
        },
        "cleanup_old_logs_task": {
            "rate_limit": "1/h",  # Once per hour
        },
    },

    # Beat scheduler (for periodic tasks)
    beat_schedule={
        # Workflow scheduler - check for due schedules every minute
        "workflow-scheduler-tick": {
            "task": "process_due_schedules_task",
            "schedule": crontab(minute="*"),  # Every minute
            "options": {"queue": "scheduled", "expires": 55}
        },

        # Daily cleanup at midnight UTC
        "daily-db-cleanup-midnight": {
            "task": "app.tasks.cleanup.cleanup_old_logs_task",
            "schedule": crontab(hour=0, minute=0),
            "args": (30,),  # 30 days retention
            "options": {"queue": "low_priority"}
        },

        # Hourly stale execution cleanup
        "hourly-stale-cleanup": {
            "task": "cleanup_stale_executions_task",
            "schedule": crontab(minute=0),  # Every hour
            "args": (24,),  # 24 hours max age
            "options": {"queue": "low_priority"}
        },

        # Worker health check every 5 minutes
        "worker-health-check": {
            "task": "health_check_task",
            "schedule": 300,  # Every 5 minutes
            "options": {"queue": "high_priority", "expires": 60}
        },
    },

    # Broker configuration
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_pool_limit=10,

    # Result backend configuration
    redis_max_connections=20,
    redis_socket_connect_timeout=5,
    redis_socket_timeout=5,
)


# ============================================================
# SIGNALS
# ============================================================

@signals.celeryd_after_setup.connect
def setup_direct_queue(sender, instance, **kwargs):
    """Called after worker setup."""
    logger.info(
        f"Celery worker started: {sender}",
        extra={"hostname": instance.hostname}
    )


@signals.worker_ready.connect
def worker_ready_handler(sender, **kwargs):
    """Called when worker is ready."""
    logger.info("Celery worker ready to accept tasks")


@signals.worker_shutting_down.connect
def worker_shutdown_handler(sig, how, exitcode, **kwargs):
    """Called when worker is shutting down."""
    logger.info(
        f"Celery worker shutting down: signal={sig}, exitcode={exitcode}"
    )


@signals.task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **extra):
    """Called before task execution."""
    logger.debug(
        f"Task starting: {task.name}",
        extra={
            "task_id": task_id,
            "task_name": task.name,
        }
    )


@signals.task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **extra):
    """Called after task execution."""
    logger.debug(
        f"Task completed: {task.name} ({state})",
        extra={
            "task_id": task_id,
            "task_name": task.name,
            "state": state,
        }
    )


@signals.task_failure.connect
def task_failure_handler(task_id, exception, args, kwargs, traceback, einfo, **extra):
    """Called on task failure."""
    logger.error(
        f"Task failed: {task_id}",
        extra={
            "task_id": task_id,
            "exception": str(exception),
            "traceback": str(einfo),
        }
    )


@signals.task_retry.connect
def task_retry_handler(request, reason, einfo, **kwargs):
    """Called on task retry."""
    logger.warning(
        f"Task retrying: {request.id}",
        extra={
            "task_id": request.id,
            "reason": str(reason),
            "retries": request.retries,
        }
    )


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_active_tasks() -> dict:
    """Gets active tasks from all workers."""
    inspect = celery_app.control.inspect()
    return {
        "active": inspect.active() or {},
        "reserved": inspect.reserved() or {},
        "scheduled": inspect.scheduled() or {},
    }


def get_worker_stats() -> dict:
    """Gets worker statistics."""
    inspect = celery_app.control.inspect()
    return {
        "stats": inspect.stats() or {},
        "registered": inspect.registered() or {},
        "ping": inspect.ping() or {},
    }


def purge_queue(queue_name: str = "default") -> int:
    """Purges all tasks from a queue."""
    return celery_app.control.purge()


def revoke_task(task_id: str, terminate: bool = False) -> None:
    """Revokes a task by ID."""
    celery_app.control.revoke(task_id, terminate=terminate)