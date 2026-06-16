import uuid
from loguru import logger
from typing import Type, Optional, Dict, Any

from src.constants import IMAGE_FILE_WEBP
from src.diffusion.base import BaseDiffusion
from src.diffusion.openai import OpenAIDiffusion
from src.diffusion.huggingface import HuggingFaceDiffusion
from src.diffusion.fal_ai import FalAIDiffusion
from src.diffusion.gemini_imagen import GeminiImagenDiffusion

from src.schemas.diffusion import BaseDiffusionConfig
from src.services.prompt_enhancer_service import PromptEnhancerService
from src.services.image_description_service import ImageDescriptionService
from src.utils.misc import convert_pil_image_to_bytes, generate_unique_id
from src.core.database.postgres import PostgresManager
from src.models.sql.models import GeneratedImage
from src.core.settings import system_setting

class ImageGenerationService:
    _provider_map: dict[str, Type[BaseDiffusion]] = {
        "openai": OpenAIDiffusion,
        "hugging_face": HuggingFaceDiffusion,
        "fal_ai": FalAIDiffusion,
        "gemini": GeminiImagenDiffusion,
    }

    def __init__(
            self, config: BaseDiffusionConfig, postgres_manager: PostgresManager
    ):
        self._config = config
        self._diffusion: Optional[BaseDiffusion] = None
        self._postgres_manager = postgres_manager
        self._prompt_enhancer = PromptEnhancerService()
        self._description_service = ImageDescriptionService()

    @property
    def diffusion(self) -> BaseDiffusion:
        if self._diffusion is None:
            provider = self._config.provider
            if provider not in self._provider_map:
                raise ValueError(f"Unsupported image generation provider: {provider}")
            diffusion_cls = self._provider_map[provider]
            self._diffusion = diffusion_cls(self._config)
        return self._diffusion

    async def generate_and_upload_image(
            self,
            user_id: str,
            original_prompt: str,
            model: Optional[str] = None,
            generate_summary: bool = False,
    ):
        """
        Orchestrates the full image generation pipeline.
        Yields status updates and final asset data. If `generate_summary` is True,
        it also generates a detailed textual description of the image for conversational context.
        """
        try:
            # 1. Enhance Prompt and get a preliminary description
            yield {"type": "status", "data": "Enhancing your creative idea..."}
            enhanced_prompt, description = await self._prompt_enhancer.enhance_prompt_and_create_description(original_prompt)

            # 2. Generate Image
            yield {"type": "status", "data": "Bringing your vision to life..."}
            generated_image = await self.diffusion.generate_image(
                prompt=enhanced_prompt,
                model=model,
                height=1024,
                width=1024,
            )

            # 3. Convert to WebP bytes
            image_bytes = convert_pil_image_to_bytes(generated_image, format="WEBP")

            # 4. Save to Database
            yield {"type": "status", "data": "Saving your creation..."}
            new_image_id = uuid.uuid4()
            async with self._postgres_manager.get_session() as session:
                db_image = GeneratedImage(
                    id=new_image_id,
                    user_id=uuid.UUID(user_id),
                    image_data=image_bytes,
                    content_type="image/webp"
                )
                session.add(db_image)
                await session.commit()

            # 5. Generate Local URL
            # Use DEFAULT_URL from settings to construct the full URL
            base_url = system_setting.DEFAULT_URL.rstrip('/')
            local_url = f"{base_url}/api/v1/file/image/{new_image_id}"

            # 6. Prepare final data packet with the preliminary description
            final_asset_data = {
                "asset_type": "image",
                "url": local_url,
                "db_id": str(new_image_id),
                "prompt": enhanced_prompt,
                "summary": description,
            }

            # 7. (Conditional) Generate a more detailed image summary and overwrite the default
            # Note: describe_image needs an accessible public URL. If the server is local-only, this might fail,
            # so we'll catch the error and fall back to the preliminary description safely.
            if generate_summary:
                yield {"type": "status", "data": "Creating an image description for our chat..."}
                try:
                    summary = await self._description_service.describe_image(image_url=local_url)
                    final_asset_data["summary"] = summary
                except Exception as desc_exc:
                    logger.warning("Failed to generate detailed image summary via Vision model (local URLs might not be accessible to cloud models): {}", desc_exc)
                    # We already have the preliminary description in `final_asset_data["summary"]`
                    pass

            yield {"type": "final_asset", "data": final_asset_data}

        except Exception as e:
            logger.exception("An error occurred during image generation pipeline: {}", e)
            yield {"type": "error", "data": "I'm sorry, I couldn't create the image. There was an issue with the generation service."}