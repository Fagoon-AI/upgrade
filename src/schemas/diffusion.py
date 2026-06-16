from pydantic import BaseModel

from typing import Literal, Optional


class BaseDiffusionConfig(BaseModel):
    provider: Literal["openai", "hugging_face", "fal_ai", "gemini"]
    api_key: Optional[str] = None