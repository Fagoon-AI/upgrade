from io import BytesIO
from typing import Optional
from typing_extensions import override

from src.providers.openai_client import aget_client, AsyncClient, OpenAIAudioCompletion
from src.schemas.speech_to_text import BaseSTTConfig
from src.speech_to_text.base import BaseSpeechToText
from openai.types.audio import Transcription

class OpenAISpeechToText(BaseSpeechToText):
    def __init__(self, config: BaseSTTConfig):
        super().__init__(config)

        assert config.provider == "openai", "requires provider as 'openai"
        self._client = None

    @property
    def client(self) -> AsyncClient:
        """Async client property"""
        if self._client is None:
            self._client = aget_client(api_key=getattr(self.config, "api_key", None))

        return self._client

    @override
    async def transcribe(
        self,
        audio: bytes,
        temperature: Optional[float] = None,
        language: Optional[str] = None,
        model: Optional[str] = "whisper-1",
        response_format: Optional[str] = "text",
        **kwargs,
    ) -> str:
        """
        Transcribes audio into text using OpenAI's Whisper model.

        Returns:
            str: Transcribed text if response_format is "json", or the full response if not.
        """
        audio_file = BytesIO(audio)
        audio_file.name = "audio.wav"

        response = await self.client.audio.transcriptions.create(
            file=audio_file,
            model=model,
            language=language,
            response_format=response_format,
            temperature=temperature,
        )
        if isinstance(response, str):
            return response
        elif isinstance(response, Transcription):
            return response.text
        else:
            raise TypeError(f"Unexpected response type from OpenAI API: {type(response)}")