from loguru import logger
from typing import Type, Optional, Dict, Any

from src.constants import IMAGE_FILE_WEBP
from src.diffusion.base import BaseDiffusion
from src.diffusion.openai import OpenAIDiffusion
from src.diffusion.huggingface import HuggingFaceDiffusion
from src.diffusion.fal_ai import FalAIDiffusion

from src.schemas.diffusion import BaseDiffusionConfig
from src.storages.file_storage import FileStorageService
from src.services.prompt_enhancer_service import PromptEnhancerService
from src.services.image_description_service import ImageDescriptionService
from src.utils.misc import convert_pil_image_to_bytes, generate_unique_id

class ImageGenerationService:
    _provider_map: dict[str, Type[BaseDiffusion]] = {
        "openai": OpenAIDiffusion,
        "hugging_face": HuggingFaceDiffusion,
        "fal_ai": FalAIDiffusion,
    }

    def __init__(
            self, config: BaseDiffusionConfig, storage_service: FileStorageService
    ):
        self._config = config
        self._diffusion: Optional[BaseDiffusion] = None
        self._storage_service = storage_service
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

            # 4. Upload to GCS
            yield {"type": "status", "data": "Uploading your creation..."}
            short_id = generate_unique_id(8)
            destination_path = f"{user_id}/images/{short_id}.webp"
            gcs_path = self._storage_service.upload_file(
                file_bytes=image_bytes,
                destination_path=destination_path,
                content_type=IMAGE_FILE_WEBP,
                file_prefix="users"
            )

            # 5. Generate Signed URL
            signed_url = self._storage_service.generate_signed_url(blob_name=gcs_path)
            if not signed_url:
                raise Exception("Failed to generate a signed URL for the uploaded image.")

            # 6. Prepare final data packet with the preliminary description
            final_asset_data = {
                "asset_type": "image",
                "url": signed_url,
                "gcs_path": gcs_path,
                "prompt": enhanced_prompt,
                "summary": description,
            }

            # 7. (Conditional) Generate a more detailed image summary and overwrite the default
            if generate_summary:
                yield {"type": "status", "data": "Creating an image description for our chat..."}
                try:
                    # This call gets a summary from the *actual* generated image
                    summary = await self._description_service.describe_image(image_url=signed_url)
                    final_asset_data["summary"] = summary
                except Exception as desc_exc:
                    logger.error("Failed to generate image summary: {}", desc_exc)
                    final_asset_data["summary"] = "A description for this image could not be generated."

            yield {"type": "final_asset", "data": final_asset_data}

        except Exception as e:
            logger.exception("An error occurred during image generation pipeline: {}", e)
            yield {"type": "error", "data": "I'm sorry, I couldn't create the image. There was an issue with the generation service."}