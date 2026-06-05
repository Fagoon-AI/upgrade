from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator

from src.schemas.chat_context import ChatContext
from src.services.response_manager import ResponseManager
from src.services.upgrade.chat import UpgradeChatService

class BaseToolHandler(ABC):
    """Abstract base class for all tool handlers."""
    def __init__(self, context: ChatContext, response_manager: ResponseManager, chat_service: UpgradeChatService):
        self.context = context
        self.response_manager = response_manager
        self.chat_service = chat_service

    @abstractmethod
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Executes the tool's logic and yields SSE formatted strings."""
        yield ""