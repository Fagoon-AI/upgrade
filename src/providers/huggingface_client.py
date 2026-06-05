from huggingface_hub import InferenceClient, AsyncInferenceClient
from huggingface_hub.inference._generated.types import ChatCompletionOutput

from src.core.settings import system_setting


def get_client() -> InferenceClient:
    return InferenceClient(api_key=system_setting.HUGGINGFACE_API_KEY)


def aget_client() -> AsyncInferenceClient:
    return AsyncInferenceClient(api_key=system_setting.HUGGINGFACE_API_KEY)


# Response Completion Type of HuggingFace for Non Streaming Response
HuggingFaceChatCompletion = ChatCompletionOutput
