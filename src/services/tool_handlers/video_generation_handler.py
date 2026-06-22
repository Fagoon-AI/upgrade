from typing import AsyncGenerator, List, Dict, Any
import uuid
import os
import asyncio
from loguru import logger

from src.services.tool_handlers.base import BaseToolHandler
from src.services.veo_video_generator import VeoVideoGenerator, VeoVideoGeneratorConfig
from src.utils.misc import get_user_latest_query
from src.schemas.upgrade_chat import ChatEventType as EventType
from src.models.video_generation_models import JobStatus, VideoJobCreate
from src.video_gen_crud.crud import create_video_job_in_db, update_job_in_db
from src.services.nosql.postgres_services import PostgresServices
from src.services.llm_enhancer import enhance_prompt_text_async

class VideoGenerationHandler(BaseToolHandler):
    """Wraps the VeoVideoGenerator to integrate with the streaming orchestrator."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        user_prompt = get_user_latest_query(conversation_history)
        user_id = str(self.context.user_id)
        job_id = str(uuid.uuid4())
        
        # 1. Start video job in DB
        async for chunk in self.response_manager.send_event(EventType.STATUS, "Enhancing prompt and initiating video job..."):
            yield chunk
        
        # Let's enhance prompt
        enhanced_prompt = user_prompt
        try:
            enhanced_prompt = await enhance_prompt_text_async(user_prompt)
        except Exception as e:
            logger.error(f"Failed to enhance prompt: {e}")
            
        # Create PostgresServices
        async with self.context.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            
            job_create_payload = VideoJobCreate(
                original_prompt=user_prompt,
                enhanced_prompt=enhanced_prompt,
                user_id=user_id,
                status=JobStatus.PENDING,
            )
            await create_video_job_in_db(pg_services=pg_services, job_id=job_id, job_data=job_create_payload)
            
        async for chunk in self.response_manager.send_event(EventType.STATUS, "Initiated video generation..."):
            yield chunk
        
        # Resolve user's custom Gemini API Key for Veo
        gemini_api_key = None
        from src.services.api_key_resolver import resolve_api_key
        import uuid
        try:
            resolved_key = await resolve_api_key(
                user_id=uuid.UUID(str(user_id)),
                provider="gemini",
                feature="chat"
            )
            if resolved_key:
                gemini_api_key = resolved_key
        except Exception as e:
            logger.error(f"Failed to resolve Gemini key for video generation: {e}")

        # 2. Run video generation using VeoVideoGenerator
        veo_config = VeoVideoGeneratorConfig(
            model="veo-2.0-generate-001",
            api_key=gemini_api_key,
        )
        video_generator = VeoVideoGenerator(config=veo_config)
        
        # Run synchronous generate_video in a threadpool to keep the server responsive
        loop = asyncio.get_running_loop()
        try:
            # Update job status in DB
            async with self.context.postgres_manager.get_session() as session:
                pg_services = PostgresServices(session)
                await update_job_in_db(
                    pg_services=pg_services,
                    job_id=job_id,
                    update_data={"status": JobStatus.PROCESSING.value, "progress": 10}
                )
                
            async for chunk in self.response_manager.send_event(EventType.STATUS, "Generating video (this may take a moment)..."):
                yield chunk
            
            # Run generate_video
            video_output_path = await loop.run_in_executor(
                None,
                lambda: video_generator.generate_video(
                    video_path="",  # Ignored as we save locally now
                    job_id=job_id,
                    prompt=enhanced_prompt
                )
            )
            
            # Success! Update DB job
            async with self.context.postgres_manager.get_session() as session:
                pg_services = PostgresServices(session)
                await update_job_in_db(
                    pg_services=pg_services,
                    job_id=job_id,
                    update_data={
                        "status": JobStatus.COMPLETED.value,
                        "progress": 100,
                        "video_url": f"/api/v1/video-generation/videos/{job_id}/download",
                        "file_path": video_output_path
                    }
                )
                
            local_url = f"/api/v1/video-generation/videos/{job_id}/download"
            
            async for chunk in self.response_manager.send_event(EventType.STATUS, "Video generated successfully!"):
                yield chunk
            
            # Send final asset to frontend
            asset_event_data = {
                "asset_type": "video",
                "url": local_url,
                "db_id": job_id,
                "prompt": enhanced_prompt,
                "summary": "Generated video based on your description."
            }
            
            # Yield events for SSE stream
            self.response_manager.append_message_chunk("Here is the video I created for you.")
            self.response_manager.add_metadata_item("generated_video", asset_event_data)
            
            # We yield both the custom asset event (aligned with image event) and the LLM response text
            async for chunk in self.response_manager.send_event(EventType.VIDEO, asset_event_data):
                yield chunk
            async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, "Here is the video I created for you."):
                yield chunk
                
        except Exception as e:
            logger.error(f"Video generation tool handler failed: {e}", exc_info=True)
            async with self.context.postgres_manager.get_session() as session:
                pg_services = PostgresServices(session)
                await update_job_in_db(
                    pg_services=pg_services,
                    job_id=job_id,
                    update_data={
                        "status": JobStatus.FAILED.value,
                        "error_message": str(e)
                    }
                )
            error_message = f"I'm sorry, I encountered an error while generating your video: {str(e)}"
            self.response_manager.append_message_chunk(error_message)
            async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, error_message):
                yield chunk
