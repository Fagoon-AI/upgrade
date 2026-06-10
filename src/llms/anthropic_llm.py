import json
from loguru import logger
from typing import Any, Dict, List, Optional, Tuple, Union

from src.llms.base import BaseLLM
from src.schemas.llm import BaseLLMConfig
from src.providers.anthropic_client import (
    aget_client,
    AsyncAnthropic,
    AnthropicChatCompletion,
)


class AnthropicLLM(BaseLLM):
    def __init__(self, config: BaseLLMConfig):
        super().__init__(config)
        assert config.provider == "anthropic", "requires provider as 'anthropic'"
        self._client = None

    @property
    def client(self) -> AsyncAnthropic:
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
        Generate a response using Anthropic chat completions API.
        """
        system_prompt, converted_messages = AnthropicLLM.__convert_to_anthropic_format(
            messages
        )

        params = {
            "model": self.config.model,
            "messages": converted_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": is_stream,
        }

        if system_prompt:
            params["system"] = system_prompt
        if response_format:
            params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.messages.create(**params)
        logger.debug(f"The response from Anthropic is: {response}")

        if is_stream:
            return response
        else:
            logger.debug(
                f"Total token usage for chat completions request is: {response.usage.model_dump()}"
            )
            return self._parse_response(response, tools)

    def _parse_response(
        self,
        response: AnthropicChatCompletion,
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Process the response based on whether tools are used or not.
        """
        if tools:
            processed_response = {
                "content": response.content[0].text,
                "tool_calls": [],
            }

            # TODO: Verify the format for function calling for anthropic and change
            if response.content[0].message.tool_calls:
                for tool_call in response.content[0].message.tool_calls:
                    processed_response["tool_calls"].append(
                        {
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments),
                        }
                    )
            return processed_response
        else:
            return response.content[0].text

    @staticmethod
    def __convert_to_anthropic_format(
        messages: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[Dict[str, str]]]:
        system_parts = []
        converted_messages = []

        append_msg = converted_messages.append
        for msg in messages:
            role = msg["role"]
            content = msg["content"].strip()

            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                append_msg({"role": role, "content": content})

        system_prompt = "\n".join(system_parts) if system_parts else None
        return system_prompt, converted_messages
