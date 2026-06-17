import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

class MockLLMModelConfig:
    def __init__(self, provider, model_id, api_key, features, is_deleted=False):
        self.provider = provider
        self.model_id = model_id
        self.api_key = api_key
        self.features = features
        self.is_deleted = is_deleted
        self.agent_ids = []
        self.workflow_ids = []

@pytest.mark.asyncio
async def test_setup_vibe_coder_environment(monkeypatch):
    # Set LITE_MODE to true first so settings don't require REDIS_URL during import / initialization
    monkeypatch.setenv("LITE_MODE", "true")
    
    # Clear other environment variables to be clean
    for env_var in ("SMART_LLM", "SMART_LLM_PROVIDER", "FAST_LLM", "FAST_LLM_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "REDIS_URL"):
        monkeypatch.delenv(env_var, raising=False)

    user_id = uuid.uuid4()
    
    # Mock PostgresManager and PostgresServices
    postgres_manager_mock = MagicMock()
    session_mock = MagicMock()
    
    # Use AsyncMock for the context manager
    postgres_manager_mock.get_session.return_value.__aenter__.return_value = session_mock
    
    # Mock configs
    mock_configs = [
        MockLLMModelConfig(
            provider="openai",
            model_id="gpt-4o",
            api_key="user-openai-key",
            features=["vibe_coder", "chat"]
        ),
        MockLLMModelConfig(
            provider="gemini",
            model_id="gemini-1.5-pro",
            api_key="user-gemini-key",
            features=["chat"]
        )
    ]
    
    # Mock PostgresServices.get_llm_model_configs_by_user_id
    from src.services.nosql.postgres_services import PostgresServices
    get_configs_mock = AsyncMock(return_value=mock_configs)
    monkeypatch.setattr(PostgresServices, "get_llm_model_configs_by_user_id", get_configs_mock)

    # Import setup_vibe_coder_environment here inside the test to prevent load-time settings errors
    from src.services.api_key_resolver import setup_vibe_coder_environment

    await setup_vibe_coder_environment(user_id, postgres_manager_mock)

    # Asserts
    assert os.environ.get("OPENAI_API_KEY") == "user-openai-key"
    assert os.environ.get("GEMINI_API_KEY") == "user-gemini-key"
    assert os.environ.get("GOOGLE_API_KEY") == "user-gemini-key"
    assert os.environ.get("SMART_LLM_PROVIDER") == "openai"
    assert os.environ.get("SMART_LLM") == "gpt-4o"
