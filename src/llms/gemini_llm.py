from typing import List
from openai import AsyncClient
from src.llms.openai_llm import OpenAILLM
from src.schemas.llm import BaseLLMConfig
from src.providers.gemini_client import aget_client
from src.core.settings import system_setting

class GeminiLLM(OpenAILLM):
    def __init__(self, config: BaseLLMConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = aget_client(self.config.api_key)
        return self._client

    async def get_embeddings(self, text: str) -> List[float]:
        """Generate text embeddings using Gemini."""
        model = self.config.model if self.config.model and "embedding" in self.config.model else "gemini-embedding-2"
        
        # We must explicitly request 1536 dimensions because our PgVector schema hardcodes Vector(1536)
        response = await self.client.embeddings.create(
            input=text,
            model=model,
            dimensions=1536
        )
        return response.data[0].embedding
