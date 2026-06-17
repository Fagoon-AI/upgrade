from pydantic import BaseModel, Field
from typing import Literal, Optional


# class BaseSTTConfig(BaseModel):
#     provider: Literal["openai", "elevenlabs"]


# class STTConfig(BaseModel):
#     provider: str = Field(default=..., description="Type of the model type used")
#     model: Optional[str] = Field(
#         default=None, description="Name of the TTS Model used for Inference Generation"
#     )
#     voice_id: Optional[str] = Field(default=None, description="Voice ID of the selected model")
#     language: Optional[str] = Field(default=None, description="Language present in the audio file")
#     temperature: Optional[float] = Field(default=None, description="Controls randomness of transcription")
#
#
# class STTInputRequest(BaseModel):
#     audio_bytes: Optional[bytes] = None
#     file_path: Optional[str] = None
#     config: STTConfig


# NEW CODE
# class BaseSTTConfig(BaseModel):
#     """Base configuration for STT providers."""
#     provider: str = Field(..., description="The STT provider to use, e.g., 'openai'.")
#     model: Optional[str] = Field(None, description="The specific model to use for transcription.")
#     language: Optional[str] = Field(None, description="The language of the audio in ISO 639-1 format.")
#     temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Sampling temperature for transcription.")
#
# class STTInputRequest(BaseModel):
#     """Defines the request body for the STT endpoint."""
#     audio_bytes: bytes = Field(..., description="The audio data to be transcribed, in bytes.")
#     config: BaseSTTConfig = Field(..., description="Configuration for the STT provider.")
#     file_path: Optional[str] = Field(None, description="An optional identifier or path for the audio file for logging.")

from pydantic import BaseModel, Field
from typing import Optional

class BaseSTTConfig(BaseModel):
    """Base configuration for STT providers."""
    provider: str = Field(..., description="The STT provider to use, e.g., 'openai'.")
    model: Optional[str] = Field("whisper-1", description="The specific model to use for transcription.")
    language: Optional[str] = Field(None, description="The language of the audio in ISO 639-1 format.")
    temperature: Optional[float] = Field(0.0, ge=0.0, le=1.0, description="Sampling temperature for transcription.")
    api_key: Optional[str] = None