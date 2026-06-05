from anthropic import AsyncAnthropic, Anthropic
from anthropic.types.message import Message

from src.core.settings import system_setting


def get_client() -> Anthropic:
    return Anthropic(
        api_key=system_setting.ANTHROPIC_API_KEY,
    )


def aget_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=system_setting.ANTHROPIC_API_KEY)


AnthropicChatCompletion = Message
