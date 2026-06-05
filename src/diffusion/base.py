from abc import ABC, abstractmethod
from PIL.Image import Image

from typing import Optional

from src.schemas.diffusion import BaseDiffusionConfig


class BaseDiffusion(ABC):
    def __init__(self, config: BaseDiffusionConfig):
        self.config = config

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Image:
        """Generate image from a prompt."""
        pass
