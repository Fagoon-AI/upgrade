from elevenlabs.client import ElevenLabs, AsyncElevenLabs

from src.core.settings import system_setting


def aget_client() -> AsyncElevenLabs:
    return AsyncElevenLabs(api_key=system_setting.ELEVENLABS_API_KEY)


def get_client() -> ElevenLabs:
    return ElevenLabs(api_key=system_setting.ELEVENLABS_API_KEY)
