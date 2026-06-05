import asyncio
from typing import Optional
from loguru import logger
from src.models.video_generation_models import JobStatus, VideoJob, VideoJobCreate
from src.services.nosql.postgres_services import PostgresServices
import uuid


async def create_video_job_in_db(
        pg_services: PostgresServices, job_id: str, job_data: VideoJobCreate
) -> VideoJob:
    """Creates a new video job in the database using PostgresServices."""
    job_dict = job_data.model_dump()
    job_dict["id"] = uuid.UUID(job_id) if len(job_id) == 36 else uuid.uuid4()
    job_dict["user_id"] = uuid.UUID(job_data.user_id) if len(job_data.user_id) == 36 else uuid.uuid4()
    return await pg_services.create_video_job(job_dict)


async def get_video_job_from_db(
        pg_services: PostgresServices, job_id: str
) -> Optional[VideoJob]:
    """Retrieves a video job by its ID from the database using PostgresServices."""
    return await pg_services.get_video_job(uuid.UUID(job_id) if len(job_id) == 36 else uuid.uuid4())


async def update_job_in_db(
        pg_services: PostgresServices, job_id: str, update_data: dict
) -> Optional[VideoJob]:
    """Updates a video job in the database using PostgresServices."""
    return await pg_services.update_video_job(uuid.UUID(job_id) if len(job_id) == 36 else uuid.uuid4(), update_data)
