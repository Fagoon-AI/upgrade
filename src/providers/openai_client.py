from openai import OpenAI, AsyncClient
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.audio.transcription import Transcription


from src.core.settings import system_setting


def get_client():
    return OpenAI(api_key=system_setting.OPENAI_API_KEY)


def aget_client():
    return AsyncClient(api_key=system_setting.OPENAI_API_KEY)


# Response Completion Type of OpenAI for Non Streaming Response
OpenAIChatCompletion = ChatCompletion
OpenAIAudioCompletion = Transcription
