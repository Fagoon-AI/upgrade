from typing import Any, Dict, List, Type, Optional, AsyncGenerator

from src.llms.anthropic_llm import AnthropicLLM
from src.llms.base import BaseLLM
from src.llms.groq_llm import GroqLLM
from src.llms.huggingface_llm import HuggingFaceLLM
from src.llms.openai_llm import OpenAILLM
from src.llms.gemini_llm import GeminiLLM
from src.schemas.llm import BaseLLMConfig
from src.utils.common import async_time_execution

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant"


class LLMService:
    _provider_map: dict[str, Type[BaseLLM]] = {
        "openai": OpenAILLM,
        "hugging_face": HuggingFaceLLM,
        "groq": GroqLLM,
        "anthropic": AnthropicLLM,
        "gemini": GeminiLLM,
    }

    def __init__(self, config: BaseLLMConfig) -> None:
        self._config = config
        self._llm: Optional[BaseLLM] = None

    @property
    def config(self) -> BaseLLMConfig:
        """Exposes the configuration for the LLM service."""
        return self._config

    @property
    def llm(self) -> BaseLLM:
        """
        Lazily initializes and returns the correct LLM provider instance.
        """
        if self._llm is None:
            provider = self._config.provider
            if provider not in self._provider_map:
                raise ValueError(f"Unsupported provider: {provider}")

            llm_cls = self._provider_map[provider]
            self._llm = llm_cls(self._config)

        return self._llm

    async def get_embeddings(self, text: str) -> List[float]:
        """Delegates embedding generation to the underlying LLM instance."""
        if hasattr(self.llm, "get_embeddings"):
            return await self.llm.get_embeddings(text)
        else:
            raise AttributeError(f"{type(self.llm).__name__} does not implement get_embeddings")

    @async_time_execution
    async def chat_completion(
        self,
        user_query: Optional[str] = None,
        system_prompt: Optional[str] = None,
        is_streaming: bool = False,
        conversations: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict]] = None,
    ):
        """
        Returns the full chat completion from the provider.
        Set `is_streaming=True` to request streaming from the provider,
        but note that this method will still aggregate and return the full output.
        """
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        try:
            if conversations:
                messages = conversations
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ]

            return await self.llm.generate(
                messages=messages,
                is_stream=is_streaming,
                tools=tools
            )

        except Exception as e:
            raise e from e

    async def chat_completion_stream(
        self,
        user_query: Optional[str] = None,
        system_prompt: Optional[str] = None,
        conversations: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streams chat completion tokens from the provider as they are generated.
        Use this for low-latency, incremental token delivery.
        """
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        if conversations:
            messages = conversations
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ]

        try:
            async for token in self.llm.generate(
                messages=messages,
                is_stream=True,
                tools=tools
            ):
                if token:
                    yield token
        except Exception as e:
            raise e from e