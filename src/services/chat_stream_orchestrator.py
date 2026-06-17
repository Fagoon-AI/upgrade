import asyncio
from typing import AsyncGenerator, List, Dict, Any
from loguru import logger
from fastapi import BackgroundTasks
import openai

from src.schemas.chat_context import ChatContext
from src.services.response_manager import ResponseManager
from src.services.file_processor import FileProcessor
from src.services.tool_handlers.factory import get_tool_handler
from src.services.query_analyzer import analyze_and_select_tools
from src.utils.misc import is_query_empty, map_conversation_command
from src.schemas.upgrade_chat import ChatEventType as EventType
from src.schemas.agent_enums import ToolType
from src.services.upgrade.chat import UpgradeChatService
from src.storages.file_storage import FileStorageService
from src.services.document_processor import DocumentProcessor
from src.services.tts import TextToSpeechServices
from src.schemas.text_to_speech import BaseTTSConfig

class ChatStreamOrchestrator:
    """
    Orchestrates the entire chat streaming process using strictly PostgreSQL.
    """

    def __init__(self, context: ChatContext, background_tasks: BackgroundTasks):
        self.context = context
        self.background_tasks = background_tasks
        document_processor = DocumentProcessor()
        self.chat_service = UpgradeChatService(context.postgres_manager, document_processor)
        self.response_manager = ResponseManager(self.chat_service, self.context.request.conversation_id)
        self.storage_service = FileStorageService()
        self.file_processor = FileProcessor(self.storage_service, self.context.postgres_manager)

    async def stream(self) -> AsyncGenerator[str, None]:
        """
        Main generator method that orchestrates the streaming workflow. It yields
        Server-Sent Events (SSE) at each step of the process.
        """
        conversation_history = []
        try:
            if is_query_empty(self.context.request.message):
                async for chunk in self.response_manager.send_event(
                        EventType.LLM_RESPONSE, "**Please ask your query to get started**"
                ):
                    yield chunk
                return

            # Phase 1: User Message Handling
            # Save the new user message to the database
            await self.chat_service.store_user_research_request(
                conversation_id=self.context.request.conversation_id,
                task=self.context.request.message
            )
            
            # Fetch the complete history
            conversation_history = await self.chat_service.get_upgrade_history(
                self.context.request.conversation_id
            )

        except Exception as e:
            logger.error("Failed during initial message processing: {}", e, exc_info=True)
            async for chunk in self.response_manager.send_event(EventType.ERROR, "Failed to process your message."):
                yield chunk
            return

        try:
            selected_tools = []
            if self.context.request.file_ids:
                async for chunk in self._process_and_stream_file_updates(conversation_history):
                    yield chunk
                selected_tools = [ToolType.GENERAL.value]
            elif self.context.request.web_search_enabled:
                selected_tools = [ToolType.WEB_SEARCH.value]
            elif self.context.request.generate_audio:
                selected_tools = [ToolType.AUDIO_GENERATION.value]
            else:
                selected_tools = await analyze_and_select_tools(
                    conversation_history, self.context.request.web_search_enabled
                )

            async for chunk in self._execute_tool_and_stream(conversation_history, selected_tools):
                yield chunk

            if self.context.request.generate_audio and self.response_manager.message:
                async for chunk in self._generate_audio_response():
                    yield chunk

            self.background_tasks.add_task(self.response_manager.save_final_response)

        # NEW: Catch the specific Rate Limit Error from the OpenAI client
        except openai.RateLimitError as e:
            logger.warning(f"Rate limit exceeded during stream: {e}")
            error_message = "The AI is currently overloaded with requests. Please wait a moment and try again."
            async for chunk in self.response_manager.send_event(EventType.ERROR, error_message):
                yield chunk

        # UPDATED: Catch-all for other errors, with a fallback check for 429 status codes
        except Exception as e:
            error_str = str(e).lower()
            
            # Fallback check in case the HTTP client throws a generic exception containing '429'
            if "429" in error_str or "too many requests" in error_str or "error" in error_str:
                logger.warning(f"Rate limit exceeded during stream: {e}")
                error_message = "The AI is currently overloaded with requests. Please wait a moment and try again."
            else:
                logger.error("Core processing error: {error}", error=str(e), exc_info=True)
                error_message = "An error occurred while generating a response."
            
            async for chunk in self.response_manager.send_event(EventType.ERROR, error_message):
                yield chunk

    async def _process_and_stream_file_updates(self, conversation_history: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Processes files and streams status updates to the client."""
        status_update = f"Processing {len(self.context.request.file_ids)} attached file(s)..."
        async for chunk in self.response_manager.send_event(EventType.STATUS, status_update):
            yield chunk

        processing_result = await self.file_processor.process_files_for_llm(self.context.request.file_ids)

        for error_msg in processing_result.errors:
            async for chunk in self.response_manager.send_event(EventType.STATUS, error_msg):
                yield chunk

        if processing_result.content:
            user_message_content = conversation_history[-1].get("content")
            conversation_history[-1]["content"] = [
                {"type": "text", "text": user_message_content},
                *processing_result.content,
            ]

    async def _execute_tool_and_stream(self, conversation_history: List[Dict[str, Any]], selected_tools: List[ToolType]) -> AsyncGenerator[str, None]:
        selected_tool = selected_tools[0] if selected_tools else ToolType.GENERAL

        command_str = map_conversation_command(selected_tools)
        async for chunk in self.response_manager.send_event(EventType.TOOL_SELECTION, f"Selected tool: {command_str}"):
            yield chunk

        ToolHandlerClass = get_tool_handler(selected_tool)
        handler = ToolHandlerClass(self.context, self.response_manager, self.chat_service)

        try:
            async for chunk in handler.execute(conversation_history):
                yield chunk
        except asyncio.CancelledError:
            raise

    async def _generate_audio_response(self) -> AsyncGenerator[str, None]:
        try:
            from src.services.api_key_resolver import resolve_api_key
            import uuid
            resolved_key = None
            try:
                resolved_key = await resolve_api_key(
                    user_id=uuid.UUID(str(self.context.user_id)),
                    provider="openai",
                    feature="chat"
                )
            except Exception as resolve_err:
                logger.error(f"Failed to resolve TTS API key in chat orchestrator: {resolve_err}")

            tts_config = BaseTTSConfig(provider="openai", model="tts-1", voice_id="alloy", api_key=resolved_key)
            tts_service = TextToSpeechServices(config=tts_config)

            audio_data = await tts_service.convert_text_to_speech_and_get_url(
                user_id=self.context.user_id,
                prompt=self.response_manager.message,
                voice_id=tts_config.voice_id,
                model=tts_config.model,
            )

            async for chunk in self.response_manager.send_event(EventType.AUDIO_OUTPUT, audio_data):
                yield chunk
        except Exception as e:
            logger.error("Failed to generate audio response: {}", e)
            async for chunk in self.response_manager.send_event(EventType.ERROR, "Failed to generate audio."):
                yield chunk
