from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.schemas.llm import BaseLLMConfig


class BaseLLM(ABC):
    def __init__(self, config: BaseLLMConfig):
        self.config = config

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        is_stream: bool = False,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        **kwargs,
    ):
        """Generate a response based on the given messages"""
        pass
