from typing import AsyncGenerator, List, Dict, Any
from src.services.tool_handlers.base import BaseToolHandler
from src.services.agents.llm_tasks import generate_general_chat_response
from src.utils.misc import get_model_id_and_service
from src.schemas.upgrade_chat import ChatEventType as EventType

class GeneralChatHandler(BaseToolHandler):
    """Handles standard conversational responses using the LLM's general knowledge."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        model, _ = get_model_id_and_service(
            path="src/tmp/model_card.yml", model_name=self.context.request.selected_model
        )
        messages = await self.chat_service.prepare_messages_with_system_prompt(
            conversation_history, self.context.user_preferences
        )
        async for chunk in generate_general_chat_response(messages=messages, model_name=model):
            if chunk:
                self.response_manager.append_message_chunk(chunk)
                async for event_chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, chunk):
                    yield event_chunk