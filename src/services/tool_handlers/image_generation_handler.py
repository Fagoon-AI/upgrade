from typing import AsyncGenerator, List, Dict, Any
from loguru import logger

from src.services.tool_handlers.base import BaseToolHandler
from src.services.imagen import ImageGenerationService
from src.schemas.diffusion import BaseDiffusionConfig
from src.storages.file_storage import FileStorageService
from src.utils.misc import get_user_latest_query
from src.schemas.upgrade_chat import ChatEventType as EventType

class ImageGenerationHandler(BaseToolHandler):
    """Wraps the ImageGenerationService to integrate with the streaming orchestrator."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        # This configuration can be made more dynamic if needed
        diffusion_config = BaseDiffusionConfig(provider="openai")
        storage_service = FileStorageService()
        image_service = ImageGenerationService(config=diffusion_config, storage_service=storage_service)
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
                message = f"Here is the image I created for you: {event_data.get('summary')}"
                self.response_manager.append_message_chunk(message)
                self.response_manager.add_metadata_item("generated_image", event_data)

                async for chunk in self.response_manager.send_event(EventType.GENERATED_ASSETS, event_data):
                    yield chunk
                async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, message):
                    yield chunk