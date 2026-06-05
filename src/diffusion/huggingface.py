from PIL.Image import Image

from typing import Optional
from src.diffusion.base import BaseDiffusion

from src.providers.huggingface_client import aget_client, AsyncInferenceClient
from src.schemas.diffusion import BaseDiffusionConfig


class HuggingFaceDiffusion(BaseDiffusion):
    def __init__(self, config: BaseDiffusionConfig):
        super().__init__(config)

        assert config.provider == "hugging_face", "requires provider as 'hugging_face'"
        self._client = None

    @property
    def client(self) -> AsyncInferenceClient:
        """Async client property."""
        if self._client is None:
            self._client = aget_client()
        return self._client

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Image:
        params = {"prompt": prompt}

        if negative_prompt:
            params["negative_prompt"] = negative_prompt

        if height:
            params["height"] = height

        if width:
            params["width"] = width

        params["model"] = model or "stabilityai/stable-diffusion-2-1"

        return await self.client.text_to_image(**params)
