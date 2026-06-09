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
        veo_config = VeoVideoGeneratorConfig(
            model="veo-2.0-generate-001",
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
