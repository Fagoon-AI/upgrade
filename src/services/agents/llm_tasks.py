from typing import Any, Dict, List, Optional

from src.schemas.agent_enums import SYSTEM_PROMPTS, SystemPrompt
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.services.map_model_provider import get_model_provider


# async def generate_general_response(
#     messages: List[Dict[str, Any]], model_name: str, max_tokens: int = 1000):
#
#     llm_service = LLMService(
#         config=BaseLLMConfig(
#             model=model_name,
#             provider=get_model_provider(model_id=model_name),
#             max_tokens=max_tokens
#         )
#     )
#
#     response_stream = await llm_service.chat_completion(
#         conversations=messages, is_streaming=True
#     )
#
#     async for chunk in response_stream:
#         content = chunk.choices[0].delta.content
#         if content is not None:
#             yield content


# This is for agent chat
async def generate_general_response(
    messages: List[Dict[str, Any]], llm_config: BaseLLMConfig
):
    if llm_config.model == "o4-mini":
        llm_config.temperature = 1.0
        llm_config.top_p = None

    llm_service = LLMService(config=llm_config)

    response_stream = await llm_service.chat_completion(
        conversations=messages,
        is_streaming=True
    )

    async for chunk in response_stream:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content is not None:
            yield content


# This is for general chat
async def generate_general_chat_response(
    messages: List[Dict[str, Any]], model_name: str, max_tokens: int = 1000):

    # 1. Try to get the provider from your YAML config
    provider = get_model_provider(model_id=model_name)
    
    # --- CRITICAL FIX: Safe Fallback Routing ---
    # If the config file misses the model, prevent the Hugging Face crash
    if not provider or provider == "hugging_face":
        if "gemini" in model_name.lower():
            provider = "openai"  # Google's API uses the OpenAI client structure
        elif "llama" in model_name.lower():
            provider = "groq"
        else:
            provider = "openai"  # Ultimate safe default
    # -------------------------------------------

    config_params = {
        "model": model_name,
        "provider": provider,
    }

    if model_name == "o4-mini":
        config_params["temperature"] = 1.0
        config_params["top_p"] = None
    else:
        config_params["max_tokens"] = max_tokens

    llm_service = LLMService(
        config=BaseLLMConfig(**config_params)
    )

    response_stream = await llm_service.chat_completion(
        conversations=messages, is_streaming=True
    )

    async for chunk in response_stream:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content is not None:
            yield content

async def acreate_title_from_history(conversations: List[Dict[str, Any]]):
    """
    Create a title from the given conversation history
    """
    title_generation_prompt = "    You are an extremely smart and helpful title generator assistant. Given a conversation, extract the subject of the conversation. Crisp, informative, ten words or less."
    prepared_message = SYSTEM_PROMPTS[SystemPrompt.CHAT_TITLE_GENERATION].format(
        chat_history=conversations
    )
    llm_service = LLMService(
        BaseLLMConfig(
            model="llama-3.3-70b-versatile",
            provider="groq",
        )
    )

    result = await llm_service.chat_completion(
        user_query=prepared_message,
        system_prompt=title_generation_prompt,
        is_streaming=False,
    )
    return result
