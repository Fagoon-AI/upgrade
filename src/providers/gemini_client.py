from openai import AsyncClient
from src.core.settings import system_setting

def aget_client():
    return AsyncClient(
        api_key=system_setting.GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
