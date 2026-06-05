from pydantic import BaseModel, Field

from src.models.enum_config import AvailableTTSModelProvider


class TTSConfig(BaseModel):
    provider: str = Field(
        default=..., description="Type of the model type used"
    )
    model: str = Field(
        default=None, description="Name of the TTS Model used for Inference Generation"
    )
    voice_id: str = Field(default=None, description="Voice ID of the selected model")


class TTSInputRequest(BaseModel):
    user_id: str
    user_prompt: str
    tts_config: TTSConfig
