from typing import AsyncGenerator, List, Dict, Any
from src.services.tool_handlers.base import BaseToolHandler
from src.services.agents.llm_tasks import generate_general_chat_response
from src.utils.misc import get_model_id_and_service
from src.schemas.upgrade_chat import ChatEventType as EventType

class SummarizationHandler(BaseToolHandler):
    """Handles requests to summarize document content."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        has_file_content = False
        last_message = conversation_history[-1]

        if isinstance(last_message.get("content"), list):
            has_file_content = any(
                isinstance(item.get("text"), str) and "--- Start of content from" in item["text"]
                or item.get("type") == "image_url"
                for item in last_message["content"]
            )

        if not has_file_content:
            error_message = "I see you've asked for a summary, but no document was provided."
            self.response_manager.append_message_chunk(error_message)
            async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, error_message):
                yield chunk
            return

        status_update = "Summarizing the document..."
        self.response_manager.add_log(status_update)
        async for chunk in self.response_manager.send_event(EventType.STATUS, status_update):
            yield chunk

        model, service_key = get_model_id_and_service(
            path="src/tmp/model_card.yml",
            model_name=self.context.request.selected_model
        )

        if not model or not service_key:
            error_message = f"Selected model '{self.context.request.selected_model}' is not supported. Please choose a different model."
            self.response_manager.add_log(error_message)
            async for chunk in self.response_manager.send_event(EventType.ERROR, error_message):
                yield chunk
            return

        messages = await self.chat_service.prepare_messages_with_system_prompt(
            conversation_history, self.context.user_preferences
        )
        messages[-1]['content'].insert(0, {"type": "text", "text": "Please summarize the key points from the document content provided below."})

        async for chunk in generate_general_chat_response(messages=messages, model_name=model):
            if chunk:
                self.response_manager.append_message_chunk(chunk)
                async for event_chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, chunk):
                    yield event_chunk