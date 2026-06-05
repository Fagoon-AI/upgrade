import fal_client
from io import BytesIO
from PIL.Image import Image
from typing import Optional
from loguru import logger
import base64

from src.diffusion.base import BaseDiffusion
from src.schemas.diffusion import BaseDiffusionConfig

class FalAIDiffusion(BaseDiffusion):
    def __init__(self, config: BaseDiffusionConfig):
        super().__init__(config)
        assert config.provider == "fal_ai", "requires provider as 'fal_ai'"
        logger.info("FalAIDiffusion provider initialized with 'fal-client'.")

    async def generate_image(
            self,
            prompt: str,
            negative_prompt: Optional[str] = None,
            height: Optional[int] = 1024,
            width: Optional[int] = 1024,
            model: Optional[str] = "fal-ai/flux/dev",
    ) -> Image:
        """
        Generates an image using the fal_client.subscribe method.
        """
        try:
            logger.info(f"Subscribing to Fal.ai model: {model}")

            handler_args = {
                "prompt": prompt,
                "negative_prompt": negative_prompt or "blurry, low quality, bad hands",
            }

            result = await fal_client.subscribe(model, arguments=handler_args)

            if "images" not in result or not result["images"]:
                raise ValueError("The result from Fal.ai did not contain image data.")

            image_data = result["images"][0]
            if image_data.get("content_type") != "image/png":
                logger.warning(f"Unexpected image format from Fal.ai: {image_data.get('content_type')}")

            image_bytes = base64.b64decode(image_data["content"])
            image = Image.open(BytesIO(image_bytes))

            logger.success("Successfully generated and decoded image from Fal.ai.")
            return image

        except Exception as e:
            logger.error(f"Fal.ai image generation failed: {e}", exc_info=True)
            raise RuntimeError("Failed to generate image from the Fal.ai service.") from e