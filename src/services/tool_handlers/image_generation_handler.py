from typing import AsyncGenerator, List, Dict, Any
import uuid
from loguru import logger

from src.services.tool_handlers.base import BaseToolHandler
from src.services.imagen import ImageGenerationService
from src.schemas.diffusion import BaseDiffusionConfig
from src.utils.misc import get_user_latest_query
from src.schemas.upgrade_chat import ChatEventType as EventType

class ImageGenerationHandler(BaseToolHandler):
    """Wraps the ImageGenerationService to integrate with the streaming orchestrator."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        
        image_provider = "gemini"
        image_api_key = None
        
        # Dynamically fetch the user's API key for image generation
        from src.services.api_key_resolver import resolve_api_key
        try:
            resolved_key = await resolve_api_key(
                user_id=uuid.UUID(str(self.context.user_id)),
                provider=image_provider,
                feature="chat"
            )
            if resolved_key:
                image_api_key = resolved_key
        except Exception as e:
            logger.error(f"Failed to resolve custom Image Generation API key in Upgrade Chat: {e}")
            
        diffusion_config = BaseDiffusionConfig(provider=image_provider, api_key=image_api_key)
        
        image_service = ImageGenerationService(
            config=diffusion_config, 
            postgres_manager=self.context.postgres_manager
        )
        user_prompt = get_user_latest_query(conversation_history)

        # The service itself is an async generator; we adapt its events to our stream
        async for event in image_service.generate_and_upload_image(
                self.context.user_id, user_prompt, generate_summary=True
        ):
            event_type = event.get("type")
            event_data = event.get("data")

            if event_type == "status":
                self.response_manager.add_log(event_data)
                async for chunk in self.response_manager.send_event(EventType.STATUS, event_data):
                    yield chunk

            elif event_type == "error":
                self.response_manager.append_message_chunk(event_data)
                async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, event_data):
                    yield chunk

            elif event_type == "final_asset":
                # The service already provides a good summary message
                image_url = event_data.get('url')
                summary = event_data.get('summary', 'Generated Image')
                message = "Here is the image I created for you."
                
                self.response_manager.append_message_chunk(message)
                self.response_manager.add_metadata_item("generated_image", event_data)

                async for chunk in self.response_manager.send_event(EventType.IMAGE, event_data):
                    yield chunk
                async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, message):
                    yield chunk