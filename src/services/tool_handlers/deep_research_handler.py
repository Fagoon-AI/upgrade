from typing import AsyncGenerator, List, Dict, Any
from src.services.tool_handlers.base import BaseToolHandler
from src.services.agents.llm_tasks import generate_general_chat_response
from src.utils.misc import get_model_id_and_service
from src.schemas.upgrade_chat import ChatEventType as EventType
from copy import deepcopy
from src.schemas.users import UserPreference

class DeepResearchHandler(BaseToolHandler):
    """Handles in-depth analysis of a query and provided documents."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        status_update = "Performing in-depth analysis based on your query and provided documents..."
        self.response_manager.add_log(status_update)
        async for chunk in self.response_manager.send_event(EventType.STATUS, status_update):
            yield chunk

        model, _ = get_model_id_and_service(
            path="src/tmp/model_card.yml",
            model_name=self.context.request.selected_model
        )

        research_preferences = deepcopy(self.context.user_preferences)
        research_preferences.system_prompt = (
            "You are a specialized research assistant. Your primary function is to analyze the user's "
            "query and the provided document context to perform in-depth research and provide a comprehensive, "
            "well-structured answer."
        )

        messages = await self.chat_service.prepare_messages_with_system_prompt(
            conversation_history, research_preferences
        )

        async for chunk in generate_general_chat_response(messages=messages, model_name=model):
            if chunk:
                self.response_manager.append_message_chunk(chunk)
                async for event_chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, chunk):
                    yield event_chunk