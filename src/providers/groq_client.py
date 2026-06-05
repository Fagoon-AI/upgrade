from groq import Groq, AsyncGroq
from groq.types.chat.chat_completion import ChatCompletion


from src.core.settings import system_setting


def get_client():
    return Groq(api_key=system_setting.GROQ_API_KEY)


def aget_client():
    return AsyncGroq(api_key=system_setting.GROQ_API_KEY)

# Response Completion Type of Groq for Non Streaming Response
GroqChatCompletion = ChatCompletion

