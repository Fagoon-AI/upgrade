from loguru import logger
from typing import Type, Optional

from src.schemas.speech_to_text import BaseSTTConfig
from src.speech_to_text.base import BaseSpeechToText
from src.speech_to_text.openai import OpenAISpeechToText
from src.utils.common import async_time_execution

class SpeechToTextService:
    _provider_map: dict[str, Type[BaseSpeechToText]] = {
        "openai": OpenAISpeechToText,
    }

    def __init__(self, config: BaseSTTConfig) -> None:
        self._config = config
        self._stt_client: Optional[BaseSpeechToText] = None

    @property
    def stt_client(self) -> BaseSpeechToText:
        if self._stt_client is None:
            provider = self._config.provider
            if provider not in self._provider_map:
                logger.error("Unsupported STT provider: {}", provider)
                raise ValueError(f"Unsupported provider: {provider}")
            stt_cls = self._provider_map[provider]
            self._stt_client = stt_cls(self._config)
        return self._stt_client

    @async_time_execution
    async def convert_speech_to_text(self, audio: bytes, **kwargs) -> str:
        try:
            logger.info("Starting speech-to-text conversion with provider '{}'.", self._config.provider)
            transcribed_text = await self.stt_client.transcribe(audio=audio, **kwargs)
            logger.success("Successfully converted speech to text.")
            return transcribed_text
        except Exception as e:
            logger.error("An error occurred during speech-to-text conversion: {}", e, exc_info=True)
            raise e from e