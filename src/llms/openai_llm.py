import json
from loguru import logger
from typing import Any, Dict, List, Optional, Union

from src.llms.base import BaseLLM
from src.schemas.llm import BaseLLMConfig
from src.providers.openai_client import aget_client, OpenAIChatCompletion, AsyncClient


class OpenAILLM(BaseLLM):
    def __init__(self, config: BaseLLMConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self) -> AsyncClient:
        """Async client property."""
        if self._client is None:
            self._client = aget_client(self.config.api_key)
        return self._client

    async def get_embeddings(self, text: str) -> List[float]:
        """Generate text embeddings using OpenAI."""
        response = await self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small"  # You might want to make this configurable
        )
        return response.data[0].embedding

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        is_stream: bool = False,
        tools: Optional[List[Dict]] = None,
        response_format: Any = None,
        tool_choice: str = "auto",
        **kwargs,
    ):
        """
        Generate a response based on the given messages using OpenAI.
        """
            
        # params = {
        #     "model": self.config.model,
        #     "messages": messages,
        #     "temperature": self.config.temperature,
        #     "top_p": self.config.top_p,
        #     "stream": is_stream,
        # }

        # 1. Start with required parameters
        params = {
            "model": self.config.model,
            "messages": messages,
            "stream": is_stream,
        }

        # 2. Define all possible optional parameters from your config
        optional_params = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
        }

        # 3. Add them to the request ONLY if they have a value
        for key, value in optional_params.items():
            if value is not None:
                params[key] = value

        if self.config.max_tokens:
            params["max_tokens"] = self.config.max_tokens

        if response_format:
            params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**params)
        logger.debug(f"the respons efrom openai is: {response}")
        if is_stream:
            return response

        else:
            logger.debug(
                f"total token usage for chat completions request is: {response.usage.model_dump()}"
            )
            return self._parse_response(response, tools)

    def _parse_response(
        self,
        response: OpenAIChatCompletion,
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Process the response based on whether tools are used or not.

        Args:
            response: The raw response from API.
            tools: The list of tools provided in the request.

        Returns:
            str or dict: The processed response.
        """
        if tools:
            processed_response = {
                "content": response.choices[0].message.content,
                "tool_calls": [],
            }

            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    processed_response["tool_calls"].append(
                        {
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments),
                        }
                    )

            return processed_response

        else:
            # Directly return the plain response, if no tools used
            return response.choices[0].message.content
