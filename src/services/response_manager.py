from typing import Any, Dict, List, Optional, AsyncGenerator
from loguru import logger

from src.schemas.common import ConversationRoleEnum
from src.services.upgrade.chat import UpgradeChatService
from src.utils.common import send_event_data
from src.schemas.upgrade_chat import ChatEventType as EventType
from src.services.chat_service import prepare_chat_insert_model


class ResponseManager:
    """
    Manages the state of the assistant's response for the duration of a stream.

    Responsibilities:
    - Holds the accumulating state (message, metadata, etc.).
    - Formats and yields Server-Sent Events (SSE) for the client.
    - Persists the final, complete assistant response to the database in the correct format.
    """
    def __init__(self, chat_service: UpgradeChatService, conversation_id: str):
        self._chat_service = chat_service
        self._conversation_id = conversation_id

        # State attributes to build the final response
        self.message: str = ""
        self.tool_selection: Optional[Dict[str, Any]] = None
        self.metadata: List[Dict[str, Any]] = []

    async def send_event(self, event_type: EventType, data: Any) -> AsyncGenerator[str, None]:
        """A generator that yields a formatted server-sent event."""
        async for chunk in send_event_data(event_type, data):
            yield chunk

    def add_log(self, log_message: str):
        """Adds a log entry to the metadata."""
        self.metadata.append({"type": "log", "data": log_message})

    def add_metadata_item(self, metadata_type: str, data: Any):
        """Adds a structured metadata item (e.g., source URLs, generated assets)."""
        self.metadata.append({"type": metadata_type, "data": data})

    def set_tool_selection(self, command_str: str):
        """Sets the tool selection information."""
        tool_data = f"**Selected Tools:** {command_str}"
        self.tool_selection = {"type": EventType.TOOL_SELECTION.value, "data": tool_data}

    def append_message_chunk(self, chunk: str):
        """Appends a chunk to the final message string."""
        self.message += chunk

    async def save_final_response(self):
        """
        Assembles the complete assistant response and persists it to the database.
        This method is designed to be run as a background task.
        """
        has_message = self.message and not self.message.isspace()
        if not has_message and not self.metadata and not self.tool_selection:
            logger.warning(f"No message, metadata, or tool selection to save for conversation {self._conversation_id}. Aborting save.")
            return

        message_to_save = []
        if has_message:
            message_to_save.append({"type": "chat", "data": self.message.strip()})
        if self.tool_selection:
            message_to_save.append(self.tool_selection)
        if self.metadata:
            message_to_save.extend(self.metadata)

        try:
            success = await self._chat_service.write_upgrade_message(
                insert_message=message_to_save,
                conversation_id=self._conversation_id,
                role=ConversationRoleEnum.ASSISTANT,
            )
            if success:
                logger.success(f"BACKGROUND SAVE: Assistant turn saved to conversation {self._conversation_id}.")
            else:
                logger.error(f"BACKGROUND SAVE: Failed to prepare assistant message for saving in convo {self._conversation_id}.")
        except Exception as e:
            logger.error(f"BACKGROUND SAVE: Error occurred while saving final response for convo {self._conversation_id}: {e}", exc_info=True)
