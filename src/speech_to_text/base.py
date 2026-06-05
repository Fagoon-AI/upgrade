from abc import ABC, abstractmethod
from typing import Optional

from src.schemas.speech_to_text import BaseSTTConfig


class BaseSpeechToText(ABC):
    def __init__(self, config: BaseSTTConfig):
        self.config = config

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        temperature: Optional[float] = None,
        language: Optional[str] = None,
        model: Optional[str] = None,
        response_format: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Convert speech to text."""
        pass
