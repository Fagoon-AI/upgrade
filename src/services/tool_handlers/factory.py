from typing import Type
from loguru import logger
from src.schemas.agent_enums import ToolType
from src.services.tool_handlers.base import BaseToolHandler
from src.services.tool_handlers.general_chat_handler import GeneralChatHandler
from src.services.tool_handlers.web_search_handler import WebSearchHandler
from src.services.tool_handlers.image_generation_handler import ImageGenerationHandler
from src.services.tool_handlers.mermaid_handler import MermaidHandler
from src.services.tool_handlers.summarization_handler import SummarizationHandler
from src.services.tool_handlers.deep_research_handler import DeepResearchHandler

def get_tool_handler(tool_type: ToolType) -> Type[BaseToolHandler]:
    """
    Factory function to retrieve the appropriate tool handler class.
    It defaults to the GeneralChatHandler if a specific handler isn't found.
    """
    handler_map = {
        ToolType.GENERAL: GeneralChatHandler,
        ToolType.WEB_SEARCH: WebSearchHandler,
        ToolType.IMAGE_GENERATION: ImageGenerationHandler,
        ToolType.MERMAID_DIAGRAM: MermaidHandler,
        ToolType.SUMMARIZATION: SummarizationHandler,
        ToolType.DEEP_RESEARCH: DeepResearchHandler,
    }

    handler_class = handler_map.get(tool_type)
    if handler_class:
        return handler_class

    logger.warning(f"No specific handler found for tool type '{tool_type}'. Defaulting to GeneralChatHandler.")
    return GeneralChatHandler