from pydantic import BaseModel

from typing import Literal


class BaseDiffusionConfig(BaseModel):
    provider: Literal["openai", "hugging_face", "fal_ai", "gemini"]