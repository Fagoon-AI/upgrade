import json
from typing import List, Dict, Optional, Any

from loguru import logger
from src.schemas.agent_enums import (
    SystemPrompt,
    TOOL_USAGE_GUIDE,
    SYSTEM_PROMPTS,
    ToolType,
)
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.utils.misc import get_user_latest_query


def _stringify_content(content: Any) -> str:
    """Helper to convert message content to a clean string for prompts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return " ".join(filter(None, texts))
    return ""


def build_prompt(
        template: SystemPrompt,
        query: str,
        history: Optional[List[Dict]] = None,
        web_search_hint: bool = False,
) -> tuple[str, str]:
    """
    Builds the (system_prompt, user_query) for the tool selection LLM.
    """
    if template != SystemPrompt.TOOL_SELECTION:
        raise ValueError(f"Unsupported prompt template: {template}")

    tool_info = "\n".join(
        f'- "{tool.value}": {desc}' for tool, desc in TOOL_USAGE_GUIDE.items()
    )

    conversation_history = history or []
    trimmed_conversation = conversation_history[-4:]

    conversation_text = "\n".join(
        f"{msg['role'].capitalize()}: {_stringify_content(msg.get('content'))}"
        for msg in trimmed_conversation
        if msg.get("content")
    )

    system_prompt_template = SYSTEM_PROMPTS[template]
    
    # --- ADD STRICT ROUTING GUARDRAILS TO BASE PROMPT ---
    routing_guardrails = (
        "\n\nCRITICAL ROUTING RULES FOR GENERAL CHAT AND SYSTEM TASKS:\n"
        "1. If the user is just saying hello, making casual conversation (e.g., 'how are you?', 'tell me a joke', 'what's up'), "
        "or asking general standalone logic/questions, you MUST return Only [\"general\"].\n"
        "2. If the user asks for the current time, date, or your name/identity, you MUST return Only [\"general\"]. Do NOT perform a web search.\n"
        "3. You must ONLY select [\"web_search\"] if the user query explicitly demands live data, fresh news, real-time lookups, or current events information."
    )
    system_prompt_template += routing_guardrails

    if web_search_hint:
        hint_text = (
            "\nHint: The user has explicitly enabled web search. Prioritize the 'web_search' tool for informational "
            "queries that require live, real-time data or lookups. However, if the query is an explicit command to generate content "
            "(e.g., 'draw a picture of...', 'create a flowchart for...'), select the corresponding generation "
            "tool ('image_generation', 'mermaid_diagram')."
        )
        system_prompt_template += hint_text

    system_prompt = system_prompt_template.format(
        tool_info=tool_info, conversation_text=conversation_text
    )

    return system_prompt, query


async def analyze_and_select_tools(
        history: List[Dict],
        web_search_enabled: bool = False,
) -> List[str]:
    """
    Uses a hybrid approach to intelligently determine which tools to activate.
    - Rule-based checks are used for simple, general queries to bypass the LLM.
    - An LLM is used for all other complex queries.
    """
    query = get_user_latest_query(history).lower().strip().rstrip('?')

    # Rule 1: Comprehensive check for casual chat, greetings, and system properties
    general_exact_matches = {
        "hello", "hi", "hey", "how are you", "what's up", "sup", "yo",
        "good morning", "good afternoon", "good evening", "how's it going",
        "who are you", "what is your name", "what's your name", "tell me a joke"
    }
    
    general_prefixes = [
        "what time", "current time", "what's the time", "what time it is", 
        "how are you", "tell me about yourself"
    ]

    if query in general_exact_matches or any(query.startswith(p) for p in general_prefixes):
        logger.info(f"Rule-based tool selection: User message '{query}' is a general query. Selecting 'general' tool.")
        return [ToolType.GENERAL.value]

    # --- FIX 1: Protect Rule 2 with the web_search_enabled toggle ---
    # Only allow rule-based web search matching if the feature is explicitly enabled by the user
    if web_search_enabled:
        web_search_triggers = [
            "who is the", "what is the current", "latest news on", "current price of", 
            "weather in", "what's the score of", "stock price of", "search for", 
            "find information on", "what are the recent developments in", "research on"
        ]
        if any(query.startswith(trigger) for trigger in web_search_triggers):
            logger.info(f"Rule-based tool selection: User message '{query}' implies a web search. Selecting 'web_search' tool.")
            return [ToolType.WEB_SEARCH.value]
    else:
        logger.debug("Skipping Rule 2 checks because web search toggle is turned OFF.")

    # Fallback: Use LLM for more complex queries that don't match simple rules.
    logger.info("No simple rules matched. Using LLM for tool analysis.")
    from src.core.settings import system_setting
    llm_service = LLMService(
        BaseLLMConfig(
            model=system_setting.FAST_MODEL_ID,
            provider=system_setting.FAST_MODEL_PROVIDER,
        )
    )
    try:
        system_prompt, user_query = build_prompt(
            template=SystemPrompt.TOOL_SELECTION,
            query=query,
            history=history,
            web_search_hint=web_search_enabled,
        )
        response = await llm_service.chat_completion(
            user_query=user_query, system_prompt=system_prompt
        )

        logger.debug(f"Tool selection LLM response: {response}")
        cleaned_response = response.strip().replace("`", "")
        if cleaned_response.startswith("json"):
            cleaned_response = cleaned_response[4:].strip()

        parsed = json.loads(cleaned_response)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array from tool selection LLM.")

        valid_tools = [tool for tool in parsed if tool in ToolType._value2member_map_]

        if not valid_tools:
            logger.warning("No valid tools selected, defaulting to general chat.")
            return [ToolType.GENERAL.value]

        logger.info(f"LLM selected tools: {valid_tools}")
        return valid_tools

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse or validate tool selection response: {e}")
        return [ToolType.GENERAL.value]
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during tool selection: {e}", exc_info=True
        )
        return [ToolType.GENERAL.value]