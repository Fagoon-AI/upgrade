from typing import Any, Dict, List, Type, Optional, AsyncGenerator
from loguru import logger

from src.llms.anthropic_llm import AnthropicLLM
from src.llms.base import BaseLLM
from src.llms.groq_llm import GroqLLM
from src.llms.huggingface_llm import HuggingFaceLLM
from src.llms.openai_llm import OpenAILLM
from src.llms.gemini_llm import GeminiLLM
from src.llms.ollama_llm import OllamaLLM
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
        "ollama": OllamaLLM,
    }

    def __init__(self, config: BaseLLMConfig) -> None:
        self._config = config
        self._llm: Optional[BaseLLM] = None

        # --- Fallback to Local Ollama Gemma 2B if API keys are missing ---
        if self._config.provider != "ollama":
            api_key = self._config.api_key
            
            # Retrieve default key from settings if not passed in config
            if not api_key:
                from src.core.settings import system_setting
                key_map = {
                    "openai": system_setting.OPENAI_API_KEY,
                    "gemini": system_setting.GEMINI_API_KEY,
                    "groq": system_setting.GROQ_API_KEY,
                    "hugging_face": system_setting.HUGGINGFACE_API_KEY,
                    "anthropic": system_setting.ANTHROPIC_API_KEY,
                }
                api_key = key_map.get(self._config.provider)
                
            # Check if the key is empty, None, or a placeholder
            is_key_missing = (
                not api_key or 
                api_key.strip() == "" or 
                api_key.startswith("YOUR_") or 
                api_key == "None"
            )
            
            if is_key_missing:
                from src.core.settings import system_setting
                
                # Check if we have a default fallback key available
                fallback_provider = system_setting.SMART_MODEL_PROVIDER
                fallback_key = getattr(system_setting, f"{fallback_provider.upper()}_API_KEY", None)
                
                if fallback_key:
                    logger.warning(
                        f"No valid API key found for provider '{self._config.provider}'. "
                        f"Failing over to default cloud fallback ({fallback_provider})..."
                    )
                    self._config.provider = fallback_provider
                    self._config.model = system_setting.SMART_MODEL_ID
                    self._config.api_key = fallback_key
                else:
                    logger.warning(
                        f"No valid API key found for provider '{self._config.provider}'. "
                        f"Failing over to local fallback model (Ollama - gemma:2b)..."
                    )
                    self._config.provider = "ollama"
                    self._config.model = "gemma:2b"
                    self._config.api_key = None

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