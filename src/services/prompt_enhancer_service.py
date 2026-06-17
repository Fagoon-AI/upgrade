import json
import re
import uuid
from loguru import logger
from typing import Tuple, Optional

from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.core.settings import system_setting

class PromptEnhancerService:
    def __init__(self):
        self.llm_service = LLMService(
            BaseLLMConfig(
                model=system_setting.FAST_MODEL_ID,
                provider=system_setting.FAST_MODEL_PROVIDER,
            )
        )

    async def enhance_prompt_and_create_description(self, original_prompt: str, user_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Takes a user's prompt and returns an enhanced, detailed prompt for a diffusion model
        and a user-facing description of the generated image.

        Returns:
            Tuple[str, str]: (enhanced_prompt, image_description)
        """
        system_prompt = """
        You are an expert creative assistant for an AI image generator. Your task is to take a user's prompt and transform it into two distinct outputs:
        1.  **A Detailed Diffusion Prompt**: Rich, visually descriptive, single paragraph. Include style, lighting, composition, mood, and visual details.
            *CRITICAL SAFETY RULE*: If the user requests an image of any real-world person, public figure, or celebrity, YOU MUST NOT use their actual name in the enhanced prompt. Instead, use a highly detailed, generic physical description and their profession or role. Using real names will cause the image generator's safety filters to block the request.
        2.  **A User-Facing Description**: Short, engaging, one-sentence description for the user. (You may use the real name here if requested).

        Respond with ONLY a valid JSON object containing two keys: "enhanced_prompt" and "image_description".
        No extra commentary, markdown fences, or text outside the JSON.
        """

        try:
            api_key = None
            if user_id:
                from src.services.api_key_resolver import resolve_api_key
                try:
                    api_key = await resolve_api_key(
                        user_id=uuid.UUID(str(user_id)),
                        provider=system_setting.FAST_MODEL_PROVIDER,
                        feature="chat"
                    )
                except Exception as e:
                    logger.error(f"Error resolving key for prompt enhancer: {e}")

            llm_service = self.llm_service
            if api_key:
                llm_service = LLMService(
                    BaseLLMConfig(
                        model=system_setting.FAST_MODEL_ID,
                        provider=system_setting.FAST_MODEL_PROVIDER,
                        api_key=api_key
                    )
                )

            response_str = await llm_service.chat_completion(
                user_query=original_prompt, system_prompt=system_prompt
            )

            # Remove any markdown code fences or leading/trailing text
            clean_str = re.search(r"\{.*\}", response_str, re.DOTALL)
            if clean_str:
                clean_str = clean_str.group(0)
            else:
                clean_str = response_str.strip()

            response_json = json.loads(clean_str)

            enhanced_prompt = str(response_json.get("enhanced_prompt", str(original_prompt)))
            image_description = str(response_json.get("image_description", "An AI-generated image."))

            logger.info("Prompt enhanced: '{}' -> '{}'", original_prompt, enhanced_prompt)
            return enhanced_prompt, image_description

        except Exception as e:
            logger.exception("Failed to enhance prompt: {}", e)
            # Always return a string for enhanced_prompt to avoid invalid_type errors
            return str(original_prompt), f"An AI-generated image based on the prompt: {original_prompt}"
