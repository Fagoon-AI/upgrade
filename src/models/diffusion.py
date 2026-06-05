from pydantic import BaseModel, Field

from typing import Optional


class DiffusionModelConfig(BaseModel):
    model: Optional[str] = Field(
        default=None, description="Name of the Diffusion Model for Image Generation"
    )
    provider: Optional[str] = Field(
        default=None, description="Name of the model provider"
    )
    height: Optional[int] = Field(None, description="Height of the image")
    width: Optional[int] = Field(None, description="Width of the image")


class ImageGenerationInputRequest(BaseModel):
    user_id: str
    prompt: str
    negative_prompt: Optional[str] = None
    diffusion_model_config: DiffusionModelConfig
