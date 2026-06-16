from openai import AsyncClient
from src.core.settings import system_setting

def aget_client(api_key: str | None = None):
    return AsyncClient(
        api_key=api_key or system_setting.GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
