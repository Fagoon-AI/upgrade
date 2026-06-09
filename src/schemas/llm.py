from pydantic import BaseModel
from typing import Optional, Literal


class BaseLLMConfig(BaseModel):
    model: str
    max_tokens: Optional[int] = None
    provider: Literal["openai", "hugging_face", "groq", "anthropic", "gemini"]
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = 0.1
