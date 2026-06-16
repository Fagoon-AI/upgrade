import requests
from io import BytesIO
from PIL import Image
from typing import Optional

from src.diffusion.base import BaseDiffusion
from src.providers.openai_client import aget_client, AsyncClient
from src.schemas.diffusion import BaseDiffusionConfig


class OpenAIDiffusion(BaseDiffusion):
    def __init__(self, config: BaseDiffusionConfig):
        super().__init__(config)

        assert config.provider == "openai", "requires provider as 'openai'"
        self._client = None

    @property
    def client(self) -> AsyncClient:
        """Async client property."""
        if self._client is None:
            # Pass the dynamically resolved api_key down to the client
            self._client = aget_client(api_key=self.config.api_key)
        return self._client

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        model: Optional[str] = None,
    ):
        params = {"prompt": prompt}

        if height and width:
            # size: Optional[Literal["256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"]]
            params["size"] = f"{height}x{width}"

        params["model"] = model or "dall-e-3"

        result = await self.client.images.generate(**params)
        image_url = result.data[0].url
        return OpenAIDiffusion._parse_response(image_url)

    @staticmethod
    def _parse_response(url: str) -> Image.Image:
        response = requests.get(url)
        image = Image.open(BytesIO(response.content))
        return image
