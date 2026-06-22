import asyncio
import uuid
from src.schemas.llm import BaseLLMConfig
from src.llms.gemini_llm import GeminiLLM
from src.services.api_key_resolver import resolve_api_key

async def test_gemini_api_key():
    print("Testing GeminiLLM custom API key passing...")
    
    custom_key = "test_custom_gemini_key_12345"
    config = BaseLLMConfig(
        provider="gemini",
        model="gemini-2.0-flash",
        temperature=0.7,
        max_tokens=100,
        api_key=custom_key
    )
    
    llm = GeminiLLM(config)
    client = llm.client
    
    print(f"Configured API Key in config: {config.api_key}")
    print(f"Resolved API Key on Client: {client.api_key}")
    
    assert client.api_key == custom_key, f"API key on client '{client.api_key}' does not match expected custom key '{custom_key}'!"
    print("SUCCESS: GeminiLLM correctly forwards the user-configured custom API key to the client!")


class MockLLMModelConfig:
    def __init__(self, provider, api_key, features):
        self.provider = provider
        self.api_key = api_key
        self.features = features
        self.agent_ids = []
        self.workflow_ids = []


class MockPostgresServices:
    def __init__(self, configs):
        self._configs = configs
    async def get_llm_model_configs_by_user_id(self, user_id):
        return self._configs


async def test_api_key_resolver_fallbacks():
    print("\nTesting api_key_resolver robust fallbacks...")
    user_id = uuid.uuid4()
    
    # 1. Config with only 'chat' feature
    configs = [
        MockLLMModelConfig(provider="gemini", api_key="resolved_gemini_key_abc", features=["chat"])
    ]
    mock_services = MockPostgresServices(configs)
    
    # Resolving with feature='agents' should trigger fallback 2b to 'chat' feature
    resolved_key = await resolve_api_key(
        user_id=user_id,
        provider="gemini",
        feature="agents",
        postgres_services=mock_services
    )
    print(f"Resolved Key for 'agents' feature (fallback to chat): {resolved_key}")
    assert resolved_key == "resolved_gemini_key_abc", f"Expected 'resolved_gemini_key_abc', but got '{resolved_key}'"
    
    # 2. Config with no matched features
    configs_no_features = [
        MockLLMModelConfig(provider="gemini", api_key="ultimate_fallback_key_xyz", features=[])
    ]
    mock_services_no_features = MockPostgresServices(configs_no_features)
    
    # Resolving with feature='agents' should trigger fallback 2c to first provider config with key
    resolved_key_fallback = await resolve_api_key(
        user_id=user_id,
        provider="gemini",
        feature="agents",
        postgres_services=mock_services_no_features
    )
    print(f"Resolved Key for 'agents' feature (ultimate fallback): {resolved_key_fallback}")
    assert resolved_key_fallback == "ultimate_fallback_key_xyz", f"Expected 'ultimate_fallback_key_xyz', but got '{resolved_key_fallback}'"
    
    print("SUCCESS: api_key_resolver robust fallback logic successfully validated!")


async def run_all_tests():
    await test_gemini_api_key()
    await test_api_key_resolver_fallbacks()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
