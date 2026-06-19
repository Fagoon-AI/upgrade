"""Lite Mode task implementations (CELERY-FREE).

These tasks contain the exact same business logic as the Celery task wrappers
but are entirely asynchronous, self-contained, and do NOT import or depend on
Celery or Redis.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.services.veo_video_generator import (
    VeoVideoGenerator,
    VeoVideoGeneratorConfig,
    VideoGenerationError,
)
from src.core.settings import get_settings
from src.services.channel_adapter.processor import process_webhook_event

log = logging.getLogger(__name__)


async def generate_video_lite(
    video_path: str,
    job_id: str,
    original_prompt: str,
    final_prompt_for_video: str,
    enhanced_prompt_text: Optional[str],
) -> None:
    log.info("Lite video generation task started for job_id: %s", job_id)
    settings = get_settings()
    pg_manager = PostgresManager(settings.DATABASE_URL)
    try:
        async with pg_manager.get_session() as session:
            db_services = PostgresServices(session)
            
            # Update job status to PROCESSING
            await db_services.update_video_job(
                uuid.UUID(job_id) if len(job_id) == 36 else None,
                {"status": "PROCESSING", "progress": 0}
            )
            log.info("Job %s successfully updated to PROCESSING.", job_id)

            log.info("Job %s: Initializing video generator...", job_id)
            
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
            log.info("Job %s: Calling video generator for video generation...", job_id)

            # Veo generation is blocking, run in a separate OS thread to avoid freezing the server
            video_output_path_or_url = await asyncio.to_thread(
                video_generator.generate_video, video_path, job_id, final_prompt_for_video
            )

            log.info(
                "Job %s: Video generation complete. Output at: %s", job_id, video_output_path_or_url
            )

            if video_output_path_or_url and (
                video_output_path_or_url.startswith("gs://") or 
                video_output_path_or_url.startswith("http://") or 
                video_output_path_or_url.startswith("https://")
            ):
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
                    "video_url": f"/api/v1/video-generation/videos/{job_id}/download",
                    "file_path": video_output_path_or_url
                }

            await db_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, update_data)
            log.info("Job %s successfully updated to COMPLETED.", job_id)

    except VideoGenerationError as e:
        log.error("Video generation specific error for job_id %s: %s", job_id, e, exc_info=True)
        error_detail = str(e)
        if hasattr(e, "__cause__") and e.__cause__:
            error_detail += f" - Caused by: {e.__cause__}"
        
        fail_data = {"status": "FAILED", "error_message": error_detail}
        async with pg_manager.get_session() as session:
            await PostgresServices(session).update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, fail_data)
        log.error("Job %s updated to FAILED with error: %s", job_id, error_detail)

    except Exception as e:
        log.error("Unexpected error in lite task for job_id %s: %s", job_id, e, exc_info=True)
        fail_data = {"status": "FAILED", "error_message": f"Unexpected error: {str(e)}"}
        async with pg_manager.get_session() as session:
            await PostgresServices(session).update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else None, fail_data)
        log.error("Job %s updated to FAILED with unexpected error: %s", job_id, str(e))
    finally:
        await pg_manager.close()


async def process_webhook_message_lite(event: dict) -> None:
    log.info("Lite webhook message task started for event: %s", event.get("message_id"))
    try:
        await process_webhook_event(event)
        log.info("Lite webhook message task finished for event: %s", event.get("message_id"))
    except Exception as e:
        log.error("Error running webhook message lite task: %s", e, exc_info=True)


# ============================================================
# LITE WORKFLOW WRAPPERS
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


async def execute_workflow_lite(
        execution_id: str,
        workflow_id: str,
        initial_input: dict,
        resume_node_id: str | None = None,
        single_node_id: str | None = None
) -> dict:
    log.info("Lite execute_workflow_lite started for execution_id: %s", execution_id)
    try:
        return await execute_workflow_logic(
            execution_id=execution_id,
            workflow_id=workflow_id,
            initial_input=initial_input,
            resume_node_id=resume_node_id,
            single_node_id=single_node_id,
        )
    except Exception as e:
        log.error("Execution failed in Lite Mode: %s", e, exc_info=True)
        await _mark_execution_failed(execution_id, str(e))
        raise


async def cancel_execution_lite(execution_id: str, reason: str = "Cancelled by user") -> dict:
    log.info("Lite cancel_execution_lite: %s", execution_id)
    return await cancel_execution_logic(execution_id, reason)


async def cleanup_stale_executions_lite(max_age_hours: int = 24) -> dict:
    log.info("Lite cleanup_stale_executions_lite")
    return await cleanup_stale_executions_logic(max_age_hours)


async def health_check_lite() -> dict:
    log.info("Lite health_check_lite")
    return health_check_logic("lite-worker")


async def process_due_schedules_lite() -> dict:
    log.info("Lite process_due_schedules_lite")
    return await _process_due_schedules_async()


async def create_schedule_from_workflow_lite(workflow_id: str, user_id: str) -> dict:
    log.info("Lite create_schedule_from_workflow_lite: %s", workflow_id)
    return await _create_schedule_from_workflow_async(workflow_id, user_id)


async def disable_workflow_schedules_lite(workflow_id: str) -> dict:
    log.info("Lite disable_workflow_schedules_lite: %s", workflow_id)
    return await _disable_workflow_schedules_async(workflow_id)


async def cleanup_old_logs_lite(retention_days: int = 30, batch_size: int = 1000) -> dict:
    log.info("Lite cleanup_old_logs_lite")
    return await _run_cleanup(retention_days, batch_size)


async def cleanup_traces_lite(retention_days: int = 7, batch_size: int = 2000) -> dict:
    log.info("Lite cleanup_traces_lite")
    return await _run_trace_cleanup(retention_days, batch_size)
