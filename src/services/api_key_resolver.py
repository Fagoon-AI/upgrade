import uuid
from typing import Optional, List
from loguru import logger
from src.core.settings import system_setting
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices

async def resolve_api_key(
    user_id: uuid.UUID,
    provider: str,
    feature: str,
    specific_id: Optional[str] = None,
    postgres_services: Optional[PostgresServices] = None
) -> Optional[str]:
    """
    Resolves the API key to use for a given user, provider, feature, and optional specific_id.
    
    Resolution hierarchy:
    1. Check if the user has a configured LLMModelConfig.
    2. If specific_id (agent_id or workflow_id) is provided and matches, use its API key.
    3. If not, match based on the requested feature ('chat', 'agents', 'workflow', 'vibe_coder').
    4. If no user-specific key is found, fallback to system_setting (system-wide .env key).
    """
    user_api_key = None
    
    # Ensure provider is lowercase for consistency
    provider = provider.lower()
    feature = feature.lower()
    
    try:
        # If postgres_services is not provided, initialize it locally
        if postgres_services is None:
            pg_manager = PostgresManager(system_setting.DATABASE_URL)
            async with pg_manager.get_session() as session:
                services = PostgresServices(session)
                configs = await services.get_llm_model_configs_by_user_id(user_id)
        else:
            configs = await postgres_services.get_llm_model_configs_by_user_id(user_id)
            
        # Filter configurations by the requested provider (lowercase match)
        provider_configs = [c for c in configs if c.provider.lower() == provider]
        
        # 1. Attempt Specific ID Match (agent_ids or workflow_ids)
        if specific_id and (feature in ("agents", "workflow")):
            for config in provider_configs:
                # agent_ids and workflow_ids are stored as JSONB list of strings
                target_ids = config.agent_ids if feature == "agents" else config.workflow_ids
                if isinstance(target_ids, list) and specific_id in target_ids:
                    if config.api_key:
                        user_api_key = config.api_key
                        logger.debug(f"Resolved API key for user {user_id} using specific {feature} id {specific_id}.")
                        break
        
        # 2. Attempt Feature Match if specific ID match didn't yield a key
        if not user_api_key:
            for config in provider_configs:
                if isinstance(config.features, list) and feature in config.features:
                    if config.api_key:
                        user_api_key = config.api_key
                        logger.debug(f"Resolved API key for user {user_id} using feature {feature}.")
                        break
                        
        # 2b. Fallback to 'chat' feature match if requested feature is 'agents' or 'workflow'
        if not user_api_key and feature in ("agents", "workflow"):
            for config in provider_configs:
                if isinstance(config.features, list) and "chat" in config.features:
                    if config.api_key:
                        user_api_key = config.api_key
                        logger.debug(f"Resolved API key for user {user_id} using fallback feature 'chat' for requested feature '{feature}'.")
                        break

        # 2c. Ultimate provider fallback: if still no key, grab the first config for this provider with an API key
        if not user_api_key:
            for config in provider_configs:
                if config.api_key:
                    user_api_key = config.api_key
                    logger.debug(f"Resolved API key for user {user_id} using first available config for provider '{provider}'.")
                    break
                        
    except Exception as e:
        logger.error(f"Error resolving API key for user {user_id}: {str(e)}")

    # 3. Fallback to system_setting if no user key was resolved
    if user_api_key:
        return user_api_key
        
    logger.debug(f"Falling back to system-wide API key for provider '{provider}'.")
    
    provider_fallback_map = {
        "openai": system_setting.OPENAI_API_KEY,
        "gemini": system_setting.GEMINI_API_KEY,
        "groq": system_setting.GROQ_API_KEY,
        "hugging_face": system_setting.HUGGINGFACE_API_KEY,
        "huggingface": system_setting.HUGGINGFACE_API_KEY,
        "elevenlabs": system_setting.ELEVENLABS_API_KEY,
        "google": system_setting.GOOGLE_API_KEY,
        "anthropic": system_setting.ANTHROPIC_API_KEY,
    }
    
    return provider_fallback_map.get(provider)
