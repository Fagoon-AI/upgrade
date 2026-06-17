import uuid
from typing import Optional
from loguru import logger
from src.services.llm import LLMService
from src.schemas.llm import BaseLLMConfig
from src.core.settings import system_setting

class ImageDescriptionService:
    def __init__(self):
        self.llm_service = LLMService(
            BaseLLMConfig(
                model=system_setting.SMART_MODEL_ID, 
                provider=system_setting.SMART_MODEL_PROVIDER
            )
        )

    async def describe_image(self, image_url: str, user_id: Optional[str] = None) -> str:
        system_prompt = (
            "You are an expert at describing images. Look at the provided image and "
            "generate a concise, one-sentence summary suitable as a caption. "
            "Focus on the main subject, setting, and mood."
        )
        
        api_key = None
        if user_id:
            from src.services.api_key_resolver import resolve_api_key
            try:
                api_key = await resolve_api_key(
                    user_id=uuid.UUID(str(user_id)),
                    provider=system_setting.SMART_MODEL_PROVIDER,
                    feature="chat"
                )
            except Exception as e:
                logger.error(f"Error resolving key for image description service: {e}")

        llm_service = self.llm_service
        if api_key:
            llm_service = LLMService(
                BaseLLMConfig(
                    model=system_setting.SMART_MODEL_ID,
                    provider=system_setting.SMART_MODEL_PROVIDER,
                    api_key=api_key
                )
            )

        summary = await llm_service.chat_completion(
            user_query="Describe this image.",
            image_url=image_url,
            system_prompt=system_prompt,
        )
        return summary
