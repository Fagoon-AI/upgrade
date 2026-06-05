from loguru import logger
from typing import Type, Optional, Dict

from src.constants import AUDIO_FILE
from src.schemas.text_to_speech import BaseTTSConfig
from src.storages.file_storage import FileStorageService
from src.text_to_speech.base import BaseTextToSpeech
from src.text_to_speech.eleven_labs import ElevenLabsTextToSpeech
from src.text_to_speech.kokoro import KokoroTextToSpeech
from src.text_to_speech.openai import OpenAITextToSpeech
from src.utils.misc import generate_unique_id
from src.utils.common import async_time_execution

class TextToSpeechServices:
    _provider_map: dict[str, Type[BaseTextToSpeech]] = {
        "openai": OpenAITextToSpeech,
        "elevenlabs": ElevenLabsTextToSpeech,
        "fagoon": KokoroTextToSpeech,
    }

    def __init__(self, config: BaseTTSConfig, storage_service: FileStorageService | None = None) -> None:
        self._config = config
        self._tts_client: BaseTextToSpeech | None = None
        self._storage_service = storage_service

    @property
    def tts_client(self) -> BaseTextToSpeech:
        if self._tts_client is None:
            provider = self._config.provider
            if provider not in self._provider_map:
                raise ValueError(f"Unsupported provider: {provider}")
            tts_cls = self._provider_map[provider]
            self._tts_client = tts_cls(self._config)
        return self._tts_client

    @property
    def storage_service(self) -> FileStorageService:
        if self._storage_service is None:
            self._storage_service = FileStorageService("GOOGLE")
        return self._storage_service

    @async_time_execution
    async def convert_text_to_speech_and_get_url(self, user_id: str, prompt: str, voice_id: str, model: Optional[str] = None) -> Dict[str, str]:
        try:
            logger.info(f"Generating audio for user '{user_id}' with provider '{self._config.provider}'.")
            audio_bytes = await self.tts_client.synthesize(text=prompt, voice_id=voice_id, model=model)

            short_id = generate_unique_id(10)
            destination_path = f"audio/{user_id}/{short_id}.mp3"

            logger.info(f"Uploading generated audio to GCS bucket at path: {destination_path}")
            gcs_path = self.storage_service.upload_file_to_workflow_folder(
                file_bytes=audio_bytes,
                destination_path=destination_path,
                content_type=AUDIO_FILE,
            )

            logger.info(f"Generating signed URL for blob: {gcs_path}")
            signed_url = self.storage_service.generate_signed_url(blob_name=gcs_path, expiration_in_hours=1)

            logger.success(f"Successfully created TTS audio and signed URL for user '{user_id}'.")
            return {"gcs_path": gcs_path, "signed_url": signed_url}

        except Exception as e:
            logger.error(f"An error occurred while converting text to speech: {e}", exc_info=True)
            raise e from e