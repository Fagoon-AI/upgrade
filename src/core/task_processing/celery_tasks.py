import time
from typing import Optional, Union
import asyncio
from loguru import logger
from src.core.task_processing.celery_app import celery_app
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.services.veo_video_generator import VeoVideoGenerator, VeoVideoGeneratorConfig, VideoGenerationError
from src.core.settings import system_setting
import uuid


async def _generate_video_job_async(
        video_path: str,
        job_id: str,
        original_prompt: str,
        final_prompt_for_video: str,
        enhanced_prompt_text: Optional[str],
        db_services: PostgresServices
):
    """
    Contains the core asynchronous logic for video generation.
    Supports strictly PostgreSQL services.
    """
    try:
        # Update job status
        await db_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, {"status": "PROCESSING", "progress": 0})
        
        logger.info("Job {} successfully updated to PROCESSING.", job_id)

        logger.info("Job {}: Initializing video generator...", job_id)
        
        # Resolve dynamic API key
        resolved_key = None
        job = await db_services.get_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None)
        user_uuid = job.user_id if job else None
        if user_uuid:
            from src.services.api_key_resolver import resolve_api_key
            try:
                resolved_key = await resolve_api_key(
                    user_id=user_uuid,
                    provider="gemini",
                    feature="chat"
                )
            except Exception as e:
                logger.error(f"Error resolving key for video generation: {e}")

        veo_config = VeoVideoGeneratorConfig(
            model="veo-2.0-generate-001",
            user_id=user_uuid,
            api_key=resolved_key,
        )
        video_generator = VeoVideoGenerator(config=veo_config)
        logger.info("Job {}: Calling video generator for video generation...", job_id)

        video_output_path_or_url = video_generator.generate_video(video_path, job_id, final_prompt_for_video)

        logger.info(
            "Job {}: Video generation complete. Output at: {}", job_id, video_output_path_or_url
        )

        if video_output_path_or_url and (video_output_path_or_url.startswith("gs://") or video_output_path_or_url.startswith("http://") or video_output_path_or_url.startswith("https://")):
            update_data = {
                "status": "COMPLETED",
                "progress": 100,
                "video_url": video_output_path_or_url,
                "file_path": None
            }
        else:
            update_data = {
                "status": "COMPLETED",
                "progress": 100,
                "video_url": f"/api/v1/videos/{job_id}/download",
                "file_path": video_output_path_or_url
            }

        await db_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, update_data)
        logger.info("Job {} successfully updated to COMPLETED with output path/URL.", job_id)

    except VideoGenerationError as e:
        logger.error("Video generation specific error for job_id {}: {}", job_id, e, exc_info=True)
        error_detail = str(e)
        if hasattr(e, '__cause__') and e.__cause__:
            error_detail += f" - Caused by: {e.__cause__}"
        
        fail_data = {"status": "FAILED", "error_message": error_detail}
        await db_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, fail_data)
        logger.error("Job {} updated to FAILED with error: {}", job_id, error_detail)

    except Exception as e:
        logger.error("Unexpected error in Celery task for job_id {}: {}", job_id, e, exc_info=True)
        fail_data = {"status": "FAILED", "error_message": f"Unexpected error: {str(e)}"}
        await db_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, fail_data)
        logger.error("Job {} updated to FAILED with unexpected error: {}", job_id, str(e))


@celery_app.task(bind=True, name="app.tasks.generate_video_task", acks_late=True, ignore_result=True)
def generate_video_task(
        self,
        video_path: str,
        job_id: str,
        original_prompt: str,
        final_prompt_for_video: str,
        enhanced_prompt_text: Optional[str],
):
    logger.info("Celery task {} started for job_id: {}", self.request.id, job_id)

    if not system_setting.DATABASE_URL:
        logger.critical("DATABASE_URL not set in Celery worker!")
        return

    pg_manager = PostgresManager(system_setting.DATABASE_URL)

    async def main():
        async with pg_manager.get_session() as session:
            pg_services = PostgresServices(session)
            await _generate_video_job_async(
                video_path, job_id, original_prompt, 
                final_prompt_for_video, enhanced_prompt_text, pg_services
            )

    try:
        asyncio.run(main())
        logger.info("Celery task {} finished for job_id: {}", self.request.id, job_id)
    except Exception as e:
        logger.error("Error running async logic in synchronous Celery task {}: {}", job_id, e, exc_info=True)
        
        async def update_status_on_failure():
            fail_data = {"status": "FAILED", "error_message": f"CRITICAL - Task runner failure: {str(e)}"}
            async with pg_manager.get_session() as session:
                await PostgresServices(session).update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, fail_data)
        
        try:
            asyncio.run(update_status_on_failure())
        except Exception as db_err:
            logger.critical("FAILED to update job {} status to FAILED: {}", job_id, db_err, exc_info=True)
    finally:
        async def close_pg(): await pg_manager.close()
        try: asyncio.run(close_pg())
        except: pass


@celery_app.task(bind=True, name="app.tasks.process_webhook_message", acks_late=True, ignore_result=True)
def process_webhook_message_task(self, event: dict):
    logger.info("Celery webhook message task {} started for event: {}", self.request.id, event.get("message_id"))

    if not system_setting.DATABASE_URL:
        logger.critical("DATABASE_URL not set in Celery worker! Cannot process webhook message.")
        return

    try:
        from src.services.channel_adapter.processor import process_webhook_event

        asyncio.run(process_webhook_event(event))
        logger.info("Celery webhook message task {} finished for event: {}", self.request.id, event.get("message_id"))
    except Exception as e:
        logger.error("Error running webhook message task {}: {}", self.request.id, e, exc_info=True)


# ============================================================
# WORKFLOW CELERY WRAPPERS
# ============================================================

from src.tasks.workflow import (
    execute_workflow_logic,
    cancel_execution_logic,
    cleanup_stale_executions_logic,
    health_check_logic,
    _mark_execution_failed,
)
from src.tasks.scheduler import (
    _process_due_schedules_async,
    _create_schedule_from_workflow_async,
    _disable_workflow_schedules_async,
)
from src.tasks.cleanup import (
    _run_cleanup,
    _run_trace_cleanup,
)


@celery_app.task(
    name="execute_workflow_task",
    bind=True,
    max_retries=3,
    soft_time_limit=3600,
    time_limit=3900,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_workflow_task(
        self,
        execution_id: str,
        workflow_id: str,
        initial_input: dict,
        resume_node_id: str | None = None
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded, Reject
    import traceback

    logger.info(f"Starting Celery workflow execution: {execution_id}")
    try:
        result = asyncio.run(
            execute_workflow_logic(
                execution_id=execution_id,
                workflow_id=workflow_id,
                initial_input=initial_input,
                resume_node_id=resume_node_id,
            )
        )
        return result
    except SoftTimeLimitExceeded:
        logger.error(f"Execution {execution_id} exceeded time limit")
        asyncio.run(_mark_execution_failed(execution_id, "Execution exceeded time limit"))
        raise Reject("Time limit exceeded", requeue=False)
    except Exception as e:
        logger.error(f"Execution {execution_id} failed: {e}\n{traceback.format_exc()}")
        if self.request.retries < self.max_retries:
            delay = 60 * (2 ** self.request.retries)
            delay = min(delay, 600)
            logger.info(f"Retrying execution {execution_id} in {delay}s")
            raise self.retry(exc=e, countdown=delay)
        asyncio.run(_mark_execution_failed(execution_id, str(e)))
        raise


@celery_app.task(name="cancel_execution_task", bind=True)
def cancel_execution_task(self, execution_id: str, reason: str = "Cancelled by user") -> dict:
    logger.info(f"Celery cancel_execution_task: {execution_id}")
    return asyncio.run(cancel_execution_logic(execution_id, reason))


@celery_app.task(name="cleanup_stale_executions_task", bind=True)
def cleanup_stale_executions_task(self, max_age_hours: int = 24) -> dict:
    logger.info(f"Celery cleanup_stale_executions_task: max_age={max_age_hours}")
    return asyncio.run(cleanup_stale_executions_logic(max_age_hours))


@celery_app.task(name="health_check_task", bind=True)
def health_check_task(self) -> dict:
    logger.info("Celery health_check_task")
    return health_check_logic(self.request.hostname or "unknown")


@celery_app.task(name="process_due_schedules_task", bind=True)
def process_due_schedules_task(self) -> dict:
    logger.info("Celery process_due_schedules_task")
    try:
        return asyncio.run(_process_due_schedules_async())
    except Exception as e:
        logger.error(f"Scheduler task failed: {e}")
        raise


@celery_app.task(name="create_schedule_from_workflow_task", bind=True)
def create_schedule_from_workflow_task(self, workflow_id: str, user_id: str) -> dict:
    logger.info(f"Celery create_schedule_from_workflow_task: workflow={workflow_id}")
    return asyncio.run(_create_schedule_from_workflow_async(workflow_id, user_id))


@celery_app.task(name="disable_workflow_schedules_task", bind=True)
def disable_workflow_schedules_task(self, workflow_id: str) -> dict:
    logger.info(f"Celery disable_workflow_schedules_task: workflow={workflow_id}")
    return asyncio.run(_disable_workflow_schedules_async(workflow_id))


@celery_app.task(name="app.tasks.cleanup.cleanup_old_logs_task", bind=True)
def cleanup_old_logs_task(self, retention_days: int = 30, batch_size: int = 1000) -> dict:
    logger.info("Celery cleanup_old_logs_task")
    return asyncio.run(_run_cleanup(retention_days, batch_size))


@celery_app.task(name="app.tasks.cleanup.cleanup_traces_task", bind=True)
def cleanup_traces_task(self, retention_days: int = 7, batch_size: int = 2000) -> dict:
    logger.info("Celery cleanup_traces_task")
    return asyncio.run(_run_trace_cleanup(retention_days, batch_size))
