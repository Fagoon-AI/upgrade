import base64
import httpx
from PIL import Image
from io import BytesIO
from typing import Optional
from loguru import logger

from src.diffusion.base import BaseDiffusion
from src.schemas.diffusion import BaseDiffusionConfig
from src.core.settings import system_setting


class GeminiImagenDiffusion(BaseDiffusion):
    def __init__(self, config: BaseDiffusionConfig):
        super().__init__(config)
        self.api_key = config.api_key or system_setting.GEMINI_API_KEY
        if not self.api_key:
             raise ValueError("GEMINI_API_KEY is missing.")

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Image.Image:
        
        # aspect_ratio handling
        aspect_ratio = "1:1"
        if height and width:
            if height > width:
                aspect_ratio = "3:4"
            elif width > height:
                aspect_ratio = "16:9"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={self.api_key}"
        
        payload = {
            "instances": [
                {"prompt": prompt}
            ],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": aspect_ratio
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            try:
                base64_img = data["predictions"][0]["bytesBase64Encoded"]
                image_bytes = base64.b64decode(base64_img)
                return Image.open(BytesIO(image_bytes))
            except (KeyError, IndexError) as e:
                logger.error(f"Unexpected response format from Gemini Imagen API: {data}")
                raise RuntimeError(f"Failed to parse generated image data: {e}")
