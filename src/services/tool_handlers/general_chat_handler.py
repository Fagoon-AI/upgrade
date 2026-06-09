from typing import AsyncGenerator, List, Dict, Any
from src.services.tool_handlers.base import BaseToolHandler
from src.services.agents.llm_tasks import generate_general_chat_response
from src.utils.misc import get_model_id_and_service
from src.schemas.upgrade_chat import ChatEventType as EventType

class GeneralChatHandler(BaseToolHandler):
    """Handles standard conversational responses using the LLM's general knowledge."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        # Attempt to get the model the user requested
        model, provider = get_model_id_and_service(
            path="src/tmp/model_card.yml", model_name=self.context.request.selected_model
        )
        
        # Fallback to the default system setting if missing or not found
        if not model:
            from src.core.settings import system_setting
            model = system_setting.FAST_MODEL_ID
            provider = system_setting.FAST_MODEL_PROVIDER
            self.response_manager.add_log(f"Requested model not found. Falling back to default: {model}")

        messages = await self.chat_service.prepare_messages_with_system_prompt(
            conversation_history, self.context.user_preferences
        )
        async for chunk in generate_general_chat_response(messages=messages, model_name=model):
            if chunk:
                self.response_manager.append_message_chunk(chunk)
                async for event_chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, chunk):
                    yield event_chunk