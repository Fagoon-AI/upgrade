from anthropic import AsyncAnthropic, Anthropic
from anthropic.types.message import Message

from src.core.settings import system_setting


def get_client(api_key: str | None = None) -> Anthropic:
    return Anthropic(
        api_key=api_key or system_setting.ANTHROPIC_API_KEY,
    )


def aget_client(api_key: str | None = None) -> AsyncAnthropic:
    return AsyncAnthropic(api_key=api_key or system_setting.ANTHROPIC_API_KEY)


AnthropicChatCompletion = Message
