from enum import Enum
from pydantic import BaseModel, Field
from typing import Literal, Optional

class BaseTTSConfig(BaseModel):
    provider: Literal["elevenlabs", "openai", "groq", "fagoon"]
    model: Optional[str] = Field(None, description="Name of the TTS Model, e.g., 'tts-1-hd'")
    voice_id: str = Field(..., description="Voice ID for the selected model/provider.")
    api_key: Optional[str] = None

class TTSRequestWithUserId(BaseModel):
    user_id: str = Field(..., description="The ID of the user requesting the TTS.")
    user_prompt: str = Field(..., min_length=1, description="The text to be converted to speech.")
    tts_config: BaseTTSConfig = Field(..., description="Configuration for the TTS provider.")

class TTSApiRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The text to be converted to speech.")
    config: BaseTTSConfig = Field(..., description="Configuration for the TTS provider.")

class ElevenLabsVoiceID(Enum):
    VOICE_ID_1 = "21m00Tcm4TlvDq8ikWAM"
    VOICE_ID_2 = "JBFqnCBsd6RMkjVDRZzb"

class ElevenLabsModel(Enum):
    ELEVENLABS_MULTILINGUAL = "eleven_multilingual_v2"