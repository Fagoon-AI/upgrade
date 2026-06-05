from abc import ABC, abstractmethod

from typing import Optional

from src.schemas.text_to_speech import BaseTTSConfig


class BaseTextToSpeech(ABC):
    def __init__(self, config: BaseTTSConfig):
        self.config = config

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """Convert text to speech."""
        pass
