import os
import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger
import uuid

from src.core.settings import system_setting
from src.video_gen_crud.crud import (create_video_job_in_db, get_video_job_from_db, update_job_in_db)
from src.services.nosql.postgres_services import PostgresServices
from src.core.globals import get_postgres_services

from src.services.llm_enhancer import enhance_prompt_text_async
from src.models.video_generation_models import (JobStatus, JobSubmissionResponse, PromptSubmit, VideoJob, VideoJobCreate)
from src.video_generation.websocket_manager import manager
from src.utils.common import generate_uuid

router = APIRouter()

@router.post(
    "/videos",
    response_model=JobSubmissionResponse,
    status_code=202,
    tags=["Video Generation"],
)
async def submit_video_prompt(
    request: Request,
    prompt_data: PromptSubmit, 
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    user_id = request.state.user_id
    job_id = str(uuid.uuid4())
    original_prompt = prompt_data.text
    enhanced_prompt_text = None
    video_path = f"workflow/{user_id}/{job_id}/{uuid.uuid4()}.mp4"

    job_create_payload = VideoJobCreate(
        original_prompt=original_prompt,
        user_id=user_id,
        status=JobStatus.PENDING,
    )

    if prompt_data.enhance_prompt:
        job_create_payload.status = JobStatus.ENHANCING
        await create_video_job_in_db(pg_services=pg_services, job_id=job_id, job_data=job_create_payload)

        try:
            enhanced_prompt_text = await enhance_prompt_text_async(original_prompt, user_id=user_id)
            final_prompt_for_video = enhanced_prompt_text
            await update_job_in_db(
                pg_services=pg_services,
                job_id=job_id,
                update_data={
                    "enhanced_prompt": enhanced_prompt_text,
                    "status": JobStatus.PENDING.value,
                },
            )
        except Exception as e:
            logger.error("Enhancement failed: {}", e)
            final_prompt_for_video = original_prompt
            await update_job_in_db(
                pg_services=pg_services,
                job_id=job_id,
                update_data={
                    "error_message": f"Prompt enhancement failed: {str(e)}",
                    "status": JobStatus.PENDING.value,
                },
            )
    else:
        final_prompt_for_video = original_prompt
        await create_video_job_in_db(pg_services=pg_services, job_id=job_id, job_data=job_create_payload)

    # Send task to the abstracted queue by name
    request.app.state.queue.enqueue(
        "generate_video_task",
        video_path=video_path,
        job_id=job_id,
        original_prompt=original_prompt,
        final_prompt_for_video=final_prompt_for_video,
        enhanced_prompt_text=enhanced_prompt_text,
    )

    return JobSubmissionResponse(
        job_id=job_id,
        video_path=video_path,
        message="Video generation task queued.",
        status_endpoint=f"/videos/{job_id}",
        websocket_endpoint=f"/ws/videos/{job_id}/status",
    )

@router.get("/videos/{job_id}", response_model=VideoJob, tags=["Video Generation"])
async def get_job_status(job_id: str, pg_services: PostgresServices = Depends(get_postgres_services)):
    job = await get_video_job_from_db(pg_services, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found.")
    return job

@router.get("/videos/{job_id}/download", tags=["Video Access"])
async def download_video(job_id: str, pg_services: PostgresServices = Depends(get_postgres_services)):
    job = await get_video_job_from_db(pg_services, job_id)
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Job not found or not ready.")

    if job.video_url and (job.video_url.startswith("http")):
        return RedirectResponse(url=job.video_url)

    if job.file_path and os.path.exists(job.file_path):
        return FileResponse(path=job.file_path, filename=os.path.basename(job.file_path), media_type="video/mp4")
    
    raise HTTPException(status_code=404, detail="Video file not found.")

@router.websocket("/ws/videos/{job_id}/status")
async def websocket_endpoint(
    websocket: WebSocket, job_id: str, request: Request
):
    pg_manager = request.app.state.postgres_manager
    await manager.connect(websocket, job_id)
    try:
        async with pg_manager.get_session() as session:
            pg_services = PostgresServices(session)
            job = await get_video_job_from_db(pg_services, job_id)
            if job:
                await manager.send_personal_message(job.model_dump(mode="json"), websocket)
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
