import uuid
from typing import Optional
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
                        
        # 2b. Fallback to 'chat' feature match if requested feature is 'agents', 'workflow', or 'vibe_coder'
        if not user_api_key and feature in ("agents", "workflow", "vibe_coder"):
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


async def setup_vibe_coder_environment(user_id: uuid.UUID, postgres_manager: PostgresManager):
    """
    Sets up the environment variables for Vibe Coder (GPT Researcher)
    based on the user's custom model configurations in Postgres.
    """
    import os
    logger.info(f"Setting up vibe coder environment for user {user_id}...")

    # Define standard environment mapping for API keys
    provider_env_map = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "hugging_face": "HUGGINGFACE_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "mistralai": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    try:
        async with postgres_manager.get_session() as session:
            services = PostgresServices(session)
            configs = await services.get_llm_model_configs_by_user_id(user_id)

        # 1. Resolve and set API keys for ALL user's configured providers.
        for config in configs:
            if config.is_deleted or not config.api_key:
                continue

            provider = config.provider.lower()
            env_var = provider_env_map.get(provider)
            if env_var:
                resolved_key = await resolve_api_key(
                    user_id=user_id,
                    provider=provider,
                    feature="vibe_coder",
                    postgres_services=services
                )
                if resolved_key:
                    os.environ[env_var] = resolved_key
                    if provider == "gemini":
                        os.environ["GOOGLE_API_KEY"] = resolved_key
                    logger.info(f"Set environment variable {env_var} for provider '{provider}'.")

        # 2. Look for the best model configuration specifically assigned to the vibe_coder feature
        best_config = None
        for config in configs:
            if not config.is_deleted and config.api_key and isinstance(config.features, list) and "vibe_coder" in config.features:
                best_config = config
                break

        if not best_config:
            for config in configs:
                if not config.is_deleted and config.api_key and isinstance(config.features, list) and "chat" in config.features:
                    best_config = config
                    break

        if not best_config:
            for config in configs:
                if not config.is_deleted and config.api_key:
                    best_config = config
                    break

        if best_config:
            provider = best_config.provider.lower()
            model_id = best_config.model_id

            provider_map = {
                "openai": "openai",
                "gemini": "google_genai",
                "google": "google_genai",
                "anthropic": "anthropic",
                "groq": "groq",
                "huggingface": "huggingface",
                "hugging_face": "huggingface",
                "mistral": "mistralai",
            }

            smart_provider = provider_map.get(provider, provider)
            os.environ["SMART_LLM_PROVIDER"] = smart_provider
            os.environ["FAST_LLM_PROVIDER"] = smart_provider

            if not model_id:
                if provider == "openai":
                    model_id = "gpt-4o"
                elif provider in ("gemini", "google"):
                    model_id = "gemini-1.5-pro"
                elif provider == "anthropic":
                    model_id = "claude-3-5-sonnet-20240620"
                elif provider == "groq":
                    model_id = "llama-3.1-70b-versatile"
                else:
                    model_id = "gpt-4o"

            os.environ["SMART_LLM"] = model_id
            os.environ["FAST_LLM"] = model_id
            logger.info(f"Configured gpt-researcher with provider '{smart_provider}' and model '{model_id}' based on user configuration.")
        else:
            logger.info("No custom user configurations found. Relying on default system vibe coder settings.")

    except Exception as e:
        logger.error(f"Error setting up vibe coder environment: {e}", exc_info=True)

