from typing import AsyncGenerator, List, Dict, Any
from loguru import logger

from src.services.tool_handlers.base import BaseToolHandler
from src.services.mermaid_service import MermaidService
from src.utils.misc import get_user_latest_query
from src.schemas.upgrade_chat import ChatEventType as EventType
from src.services.agents.llm_tasks import generate_general_chat_response


class MermaidHandler(BaseToolHandler):
    """Handles the generation of Mermaid.js diagram code and its description."""

    async def _generate_description_for_code(self, user_prompt: str, mermaid_code: str) -> str:
        """Generates a brief, user-friendly description of the Mermaid diagram."""
        logger.info("Generating description for the created Mermaid diagram.")
        system_prompt = (
            "You are a helpful assistant. Based on the user's request and the generated Mermaid.js code, "
            "provide a short, one or two-sentence summary of what the diagram represents. "
            "Your tone should be helpful and concise. Do not talk about the code itself, but about the process it visualizes. "
            "Start your response with a phrase like 'Here is the diagram you requested. It illustrates...'."
        )

        description_prompt = (
            f"Original User Request: '{user_prompt}'\n\n"
            f"Generated Mermaid Code:\n```mermaid\n{mermaid_code}\n```"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": description_prompt}
        ]

        try:
            model_name = self.context.request.selected_model
            full_description = "".join([
                chunk async for chunk in generate_general_chat_response(messages=messages, model_name=model_name)
            ])

            if not full_description.strip():
                return "I've generated the Mermaid diagram code for you."

            return full_description.strip()
        except Exception as e:
            logger.error(f"Failed to generate description for Mermaid code: {e}")
            return "I've generated the Mermaid diagram code for you."

    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        mermaid_service = MermaidService()
        user_prompt = get_user_latest_query(conversation_history)
        selected_llm_model = self.context.request.selected_model

        try:
            # Step 1: Generate the Mermaid code
            status_update = "Crafting your diagram structure..."
            self.response_manager.add_log(status_update)
            async for chunk in self.response_manager.send_event(EventType.STATUS, status_update):
                yield chunk

            markdown_code = await mermaid_service.generate_mermaid_code(user_prompt, selected_llm_model)

            # Step 2: Send the generated diagram asset to the user
            asset_data = {"asset_type": "mermaid", "code": markdown_code}
            self.response_manager.add_metadata_item("generated_asset", asset_data)
            async for chunk in self.response_manager.send_event(EventType.GENERATED_ASSETS, asset_data):
                yield chunk

            # Step 3: Generate a meaningful description for the diagram
            status_update = "Finalizing the explanation..."
            self.response_manager.add_log(status_update)
            async for chunk in self.response_manager.send_event(EventType.STATUS, status_update):
                yield chunk

            final_message = await self._generate_description_for_code(user_prompt, markdown_code)

            # Step 4: Stream the final descriptive message to the user
            self.response_manager.append_message_chunk(final_message)
            async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, final_message):
                yield chunk

        except (ValueError, RuntimeError) as e:
            logger.error(f"Failed to generate Mermaid diagram code: {e}", exc_info=True)
            error_message = f"I'm sorry, I encountered an error creating the diagram: {str(e)}"
            self.response_manager.append_message_chunk(error_message)
            async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, error_message):
                yield chunk