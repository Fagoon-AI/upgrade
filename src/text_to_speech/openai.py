from typing import Optional
from typing_extensions import override

from src.providers.openai_client import aget_client, AsyncClient
from src.schemas.text_to_speech import BaseTTSConfig
from src.text_to_speech.base import BaseTextToSpeech


class OpenAITextToSpeech(BaseTextToSpeech):
    def __init__(self, config: BaseTTSConfig):
        super().__init__(config)

        assert config.provider == "openai", "requires provider as 'openai"

        self._client = None

    @property
    def client(self) -> AsyncClient:
        """Async client property"""
        if self._client is None:
            self._client = aget_client()

        return self._client

    @override
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = "nova",
        model: Optional[str] = "tts-1",
    ) -> bytes:
        """
        Synthesize speech from text using OpenAI API.

        Returns:
        - bytes: Binary audio data of the synthesized speech.
        """
        response = await self.client.audio.speech.create(
            input=text, voice=voice_id, model=model, response_format="mp3"
        )
        return response.read()
