from io import BytesIO
from typing import Optional
from typing_extensions import override

from src.providers.elevenlabs_client import aget_client, AsyncElevenLabs
from src.schemas.speech_to_text import BaseSTTConfig
from src.speech_to_text.base import BaseSpeechToText


class ElevenLabsSpeechToText(BaseSpeechToText):
    def __init__(self, config: BaseSTTConfig):
        super().__init__(config)

        assert config.provider == "elevenlabs", "requires provider as 'elevenlabs"
        self._client = None

    @property
    def client(self) -> AsyncElevenLabs:
        """Async client property"""
        if self._client is None:
            self._client = aget_client(api_key=getattr(self.config, "api_key", None))

        return self._client

    @override
    async def transcribe(
        self,
        audio: bytes,
        language: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Transcribes audio into text using Eleven Labs model.

        Returns:
            str: The recognized speech as text.
        """
        audio_file = BytesIO(audio)
        audio_file.name = "audio.wav"

        response = await self.client.speech_to_text.convert(
            model_id=model or "scribe_v1",
            file=audio_file,
            language_code=language or "eng",
        )

        return response.text
