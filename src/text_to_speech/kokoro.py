from typing import Optional
from typing_extensions import override

from src.providers.kokoro_client import get_client
from src.schemas.text_to_speech import BaseTTSConfig
from src.text_to_speech.base import BaseTextToSpeech

from src.utils.misc import convert_samples_to_bytes


class KokoroTextToSpeech(BaseTextToSpeech):
    def __init__(self, config: BaseTTSConfig):
        super().__init__(config)

        assert config.provider == "fagoon", "requires provider as 'fagoon"

        self._client = None

    @property
    def client(self):
        """Async client property"""
        if self._client is None:
            self._client = get_client()

        return self._client

    @override
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = "bf_emma",
        model: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """
        Synthesize speech from text using Kokoro.

        Returns:
        - bytes: Binary audio data of the synthesized speech.
        """
        audio_array, sample_rate = self.client.create(
            text=text,
            voice=voice_id,
            speed=1.0,
            lang="en-us",
        )
        return convert_samples_to_bytes(audio_array, sample_rate)
