from loguru import logger
from typing import Any, Dict, List

from src.constants import IMAGE_FILE
from src.schemas.agents_chat import EventType
from src.schemas.agent_enums import SYSTEM_PROMPTS, SystemPrompt
from src.diffusion.openai import OpenAIDiffusion
from src.schemas.llm import BaseLLMConfig
from src.schemas.diffusion import BaseDiffusionConfig
from src.services.llm import LLMService
from src.storages.file_storage import FileStorageService

from src.utils.common import send_event_data
from src.utils.misc import (
    convert_pil_image_to_bytes,
    get_user_latest_query,
    generate_unique_id,
)


class AgentImageGeneration:
    def __init__(self, chat_history: List[Dict[str, Any]] = None):
        self.file_manager = FileStorageService()

        if chat_history is None:
            chat_history = []

        self.chat_history = chat_history
        self.user_query = get_user_latest_query(self.chat_history)

    async def generate_image_for_agent(
        self, agent_id: str, user_id: str, chat_history_records: List[Dict[str, Any]]
    ):
        async for event in send_event_data(
            EventType.STATUS, "**Enhancing original query for image generation**"
        ):
            chat_history_records.append(event)
            yield event

        enhanced_query = await self.enhance_user_query()
        logger.debug(f"Enhanced user query is: {enhanced_query}")

        async for event in send_event_data(
            EventType.STATUS,
            f"**Enhanced prompt for image generation**: {enhanced_query}",
        ):
            chat_history_records.append(event)
            yield event

    
        openai_llm = OpenAIDiffusion(config=BaseDiffusionConfig(provider="openai"))
        generated_image = await openai_llm.generate_image(
            prompt=enhanced_query, model="dall-e-3"
        )

        # # TODO: Later can optimize this properly
        # # Convert PIL image to bytes and save to Google Storage
        image_bytes = convert_pil_image_to_bytes(generated_image, format="PNG")
        file_path = self.file_manager.upload_file_to_agent_folder(
            file_bytes=image_bytes,
            destination_path=f"{user_id}/{agent_id}/{f'{generate_unique_id(6)}.png'}",
            content_type=IMAGE_FILE,
        )

        async for payload in send_event_data(EventType.IMAGE, file_path):
            chat_history_records.append(payload)
            yield payload

    async def enhance_user_query(self):
        # conversation = history or []
        # conversation.append({"role": "user", "content": original_query})

        # Keep only the last 4 messages (i.e., last 2 interactions)
        # trimmed_conversation = conversation[-4:]

        enhancer_prompt = SYSTEM_PROMPTS[SystemPrompt.IMAGE_ENHANCER].format(
            user_prompt=self.user_query, conversation_history=self.chat_history[-4:]
        )
        llm_service = LLMService(
            BaseLLMConfig(
                model="llama-3.3-70b-versatile",
                provider="groq",
            )
        )

        response = await llm_service.chat_completion(
            user_query=self.user_query,
            system_prompt=enhancer_prompt,
            is_streaming=False,
        )
        return response
