from huggingface_hub import InferenceClient, AsyncInferenceClient
from huggingface_hub.inference._generated.types import ChatCompletionOutput

from src.core.settings import system_setting


def get_client(api_key: str | None = None) -> InferenceClient:
    return InferenceClient(api_key=api_key or system_setting.HUGGINGFACE_API_KEY)


def aget_client(api_key: str | None = None) -> AsyncInferenceClient:
    return AsyncInferenceClient(api_key=api_key or system_setting.HUGGINGFACE_API_KEY)


# Response Completion Type of HuggingFace for Non Streaming Response
HuggingFaceChatCompletion = ChatCompletionOutput
