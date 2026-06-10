from src.llms.openai_llm import OpenAILLM
from src.schemas.llm import BaseLLMConfig
from src.providers.gemini_client import aget_client

class GeminiLLM(OpenAILLM):
    def __init__(self, config: BaseLLMConfig):
        super(OpenAILLM, self).__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = aget_client()
        return self._client
