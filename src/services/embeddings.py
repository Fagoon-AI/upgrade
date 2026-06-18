import uuid
from typing import Optional
from loguru import logger
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.services.api_key_resolver import resolve_api_key

async def get_embedding_service(user_id: str, agent_id: Optional[str] = None) -> LLMService:
    """
    Dynamically resolve an embedding service based on the user's available API keys.
    Prefers OpenAI, falls back to Gemini.
    """
    uid = uuid.UUID(str(user_id))
    
    # Try OpenAI first
    try:
        openai_key = await resolve_api_key(uid, "openai", "agents", agent_id)
        if openai_key:
            logger.info("Using OpenAI for embeddings.")
            return LLMService(config=BaseLLMConfig(
                provider="openai",
                model="text-embedding-3-small",
                api_key=openai_key
            ))
    except Exception as e:
        logger.debug(f"Failed to resolve OpenAI key for embeddings: {e}")

    # Fallback to Gemini
    try:
        gemini_key = await resolve_api_key(uid, "gemini", "agents", agent_id)
        if gemini_key:
            logger.info("Using Gemini for embeddings.")
            return LLMService(config=BaseLLMConfig(
                provider="gemini",
                model="gemini-embedding-2",
                api_key=gemini_key
            ))
    except Exception as e:
        logger.debug(f"Failed to resolve Gemini key for embeddings: {e}")

    # If all else fails, rely on system defaults or raise
    logger.warning("No user-specific API keys found for embeddings. Falling back to system defaults.")
    from src.core.settings import system_setting
    if system_setting.OPENAI_API_KEY:
        return LLMService(config=BaseLLMConfig(provider="openai", model="text-embedding-3-small", api_key=system_setting.OPENAI_API_KEY))
    if system_setting.GEMINI_API_KEY:
        return LLMService(config=BaseLLMConfig(provider="gemini", model="gemini-embedding-2", api_key=system_setting.GEMINI_API_KEY))

    raise ValueError("No valid embedding provider could be resolved for the user.")
