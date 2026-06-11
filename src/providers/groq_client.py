from groq import Groq, AsyncGroq
from groq.types.chat.chat_completion import ChatCompletion


from src.core.settings import system_setting


def get_client(api_key: str | None = None):
    return Groq(api_key=api_key or system_setting.GROQ_API_KEY)


def aget_client(api_key: str | None = None):
    return AsyncGroq(api_key=api_key or system_setting.GROQ_API_KEY)

# Response Completion Type of Groq for Non Streaming Response
GroqChatCompletion = ChatCompletion

