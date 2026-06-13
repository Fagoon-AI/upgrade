from PIL import Image
from io import BytesIO
from typing import Optional
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

from src.diffusion.base import BaseDiffusion
from src.schemas.diffusion import BaseDiffusionConfig


class GeminiImagenDiffusion(BaseDiffusion):
    def __init__(self, config: BaseDiffusionConfig):
        super().__init__(config)
        # vertexai needs to be initialized. Assuming it's initialized globally 
        # or handle initialization here if required. 
        # For simplicity, we assume vertexai.init() is called elsewhere or 
        # that the environment is set up.
        self._model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")

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
            # Simple heuristic
            if height > width:
                aspect_ratio = "3:4"
            elif width > height:
                aspect_ratio = "16:9"

        response = self._model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio=aspect_ratio,
        )

        return response.images[0]._pil_image # Assuming _pil_image access or convert
