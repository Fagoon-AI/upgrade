import json
from loguru import logger
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from ollama import AsyncClient

from src.llms.base import BaseLLM
from src.schemas.llm import BaseLLMConfig

class OllamaLLM(BaseLLM):
    def __init__(self, config: BaseLLMConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self) -> AsyncClient:
        """Lazily initialize async Ollama client."""
        if self._client is None:
            self._client = AsyncClient()
        return self._client

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        is_stream: bool = False,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        **kwargs,
    ):
        """Generate response using local Ollama model."""
        params = {
            "model": self.config.model,
            "messages": messages,
            "stream": is_stream,
        }

        # Map base configuration parameters to Ollama format
        options = {}
        if self.config.temperature is not None:
            options["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            options["top_p"] = self.config.top_p
        if self.config.max_tokens is not None:
            options["num_predict"] = self.config.max_tokens  # num_predict is Ollama's max_tokens
        
        if options:
            params["options"] = options

        if tools:
            # Pass tools down to Ollama (supported in modern Ollama for model function calling)
            params["tools"] = tools

        try:
            if is_stream:
                return self._generate_stream(params)
            else:
                response = await self.client.chat(**params)
                logger.debug(f"Ollama response: {response}")
                return self._parse_response(response, tools)
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise e

    async def _generate_stream(self, params: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Streams string tokens from Ollama chat completions."""
        try:
            async for chunk in await self.client.chat(**params):
                yield chunk.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Ollama streaming failed: {e}")
            raise e

    def _parse_response(self, response: Dict[str, Any], tools: Optional[List[Dict]] = None) -> Union[str, Dict[str, Any]]:
        """Parse non-streaming Ollama responses."""
        message = response.get("message", {})
        content = message.get("content", "")
        
        if tools and message.get("tool_calls"):
            processed_response = {
                "content": content,
                "tool_calls": [],
            }
            for tool_call in message.get("tool_calls", []):
                function = tool_call.get("function", {})
                processed_response["tool_calls"].append({
                    "name": function.get("name"),
                    "arguments": function.get("arguments", {}),
                })
            return processed_response
        return content
