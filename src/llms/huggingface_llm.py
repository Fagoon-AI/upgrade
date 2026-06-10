import json
from typing import Any, Dict, List, Optional, Union

from src.llms.base import BaseLLM
from src.schemas.llm import BaseLLMConfig
from src.providers.huggingface_client import (
    aget_client,
    HuggingFaceChatCompletion,
    AsyncInferenceClient,
)


class HuggingFaceLLM(BaseLLM):
    def __init__(self, config: BaseLLMConfig):
        super().__init__(config)

        assert config.provider == "hugging_face", "requires provider as 'hugging_face'"
        self._client = None

    @property
    def client(self) -> AsyncInferenceClient:
        """Async client property."""
        if self._client is None:
            self._client = aget_client(self.config.api_key)
        return self._client

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
        params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": is_stream
        }

        if response_format:
            params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**params)
        if is_stream:
            return response

        else:
            return self._parse_response(response, tools)


    def _parse_response(
        self,
        response: HuggingFaceChatCompletion,
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
            return response.choices[0].message.content
