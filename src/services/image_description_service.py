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

    async def describe_image(self, image_url: str) -> str:
        system_prompt = (
            "You are an expert at describing images. Look at the provided image and "
            "generate a concise, one-sentence summary suitable as a caption. "
            "Focus on the main subject, setting, and mood."
        )
        summary = await self.llm_service.chat_completion(
            user_query="Describe this image.",
            image_url=image_url,
            system_prompt=system_prompt,
        )
        return summary