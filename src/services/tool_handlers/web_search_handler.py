from typing import AsyncGenerator, List, Dict, Any
from loguru import logger
from src.services.tool_handlers.base import BaseToolHandler
from src.services.web_search_service import WebSearchService
from src.utils.misc import get_user_latest_query
from src.schemas.upgrade_chat import ChatEventType as EventType

class WebSearchHandler(BaseToolHandler):
    """Wraps the WebSearchService to integrate with the streaming orchestrator."""
    async def execute(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        # 1. Robustly check for and retrieve all required service dependencies from the context
        if not hasattr(self.context, 'http_client') or not self.context.http_client:
            logger.critical("Programming Error: httpx.AsyncClient not found in ChatContext.")
            raise RuntimeError("httpx.AsyncClient not found in the execution context.")

        if not hasattr(self.context, 'crawl_service') or not self.context.crawl_service:
            logger.critical("Programming Error: Crawl4AIService not found in ChatContext.")
            raise RuntimeError("Crawl4AIService not found in the execution context.")

        async_client = self.context.http_client
        crawler_service = self.context.crawl_service
        
        # --- FIX: Default to a safe model if selected_model is missing ---
        from src.core.settings import system_setting
        selected_model = self.context.request.selected_model or system_setting.FAST_MODEL_ID

        # Resolve custom Groq API key if user has one configured
        groq_api_key = None
        from src.services.api_key_resolver import resolve_api_key
        import uuid
        try:
            resolved_api_key = await resolve_api_key(
                user_id=uuid.UUID(str(self.context.user_id)),
                provider="groq",
                feature="chat"
            )
            if resolved_api_key:
                groq_api_key = resolved_api_key
        except Exception as e:
            logger.error(f"Failed to resolve Groq API key for web search: {e}")

        # 2. Instantiate the service with all its required dependencies, including the selected_model and keys
        web_search_service = WebSearchService(
            query=get_user_latest_query(conversation_history),
            async_client=async_client,
            crawler_service=crawler_service,
            selected_model=selected_model,
            history=conversation_history,
            groq_api_key=groq_api_key,
            user_id=self.context.user_id
        )

        # 3. Execute the service and stream events
        async for event in web_search_service.search_and_respond():
            event_type = event["type"]
            event_data = event["data"]

            if event_type == "status":
                self.response_manager.add_log(event_data)
                async for chunk in self.response_manager.send_event(EventType.STATUS, event_data):
                    yield chunk
            elif event_type == "metadata":
                self.response_manager.add_metadata_item("source_urls", event_data.get("source_urls", []))
                async for chunk in self.response_manager.send_event(EventType.METADATA, event_data):
                    yield chunk
            elif event_type == "llm_token":
                self.response_manager.append_message_chunk(event_data)
                async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, event_data):
                    yield chunk
            elif event_type == "final_response":
                self.response_manager.append_message_chunk(event_data)
                async for chunk in self.response_manager.send_event(EventType.LLM_RESPONSE, event_data):
                    yield chunk