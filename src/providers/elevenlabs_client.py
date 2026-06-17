from typing import Optional
from elevenlabs.client import ElevenLabs, AsyncElevenLabs

from src.core.settings import system_setting


def aget_client(api_key: Optional[str] = None) -> AsyncElevenLabs:
    return AsyncElevenLabs(api_key=api_key or system_setting.ELEVENLABS_API_KEY)


def get_client(api_key: Optional[str] = None) -> ElevenLabs:
    return ElevenLabs(api_key=api_key or system_setting.ELEVENLABS_API_KEY)
