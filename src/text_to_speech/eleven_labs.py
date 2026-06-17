from typing import Optional, AsyncIterator
from typing_extensions import override

from src.providers.elevenlabs_client import aget_client, AsyncElevenLabs
from src.schemas.text_to_speech import BaseTTSConfig, ElevenLabsVoiceID, ElevenLabsModel
from src.text_to_speech.base import BaseTextToSpeech


class ElevenLabsTextToSpeech(BaseTextToSpeech):
    def __init__(self, config: BaseTTSConfig):
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
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize speech from text using ElevenLabs API.

        Uses default voice/model if none provided or invalid.
        """
        stream = self.client.text_to_speech.convert(
            text=text,
            voice_id=voice_id or ElevenLabsVoiceID.VOICE_ID_1.value,
            model_id=model or ElevenLabsModel.ELEVENLABS_MULTILINGUAL.value,
        )

        return await stream_to_bytes(stream)


async def stream_to_bytes(stream: AsyncIterator[bytes]) -> bytes:
    """
    Aggregates an asynchronous byte stream into a single bytes object.
    """
    return b"".join([chunk async for chunk in stream])
