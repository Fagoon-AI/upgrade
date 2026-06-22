import asyncio
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService

async def test_fallback():
    print("Testing LLM Fallback mechanism...")
    
    # Let's request OpenAI with empty api key
    config = BaseLLMConfig(
        provider="openai",
        model="gpt-4o",
        temperature=0.7,
        max_tokens=100,
        api_key=""
    )
    
    # We expect LLMService to fallback to ollama and configured fallback model!
    from src.core.settings import system_setting
    service = LLMService(config)
    print(f"Resulting Provider: {service.config.provider}")
    print(f"Resulting Model: {service.config.model}")
    
    assert service.config.provider == "ollama", "Provider did not failover to ollama!"
    assert service.config.model == system_setting.FALLBACK_MODEL_NAME, f"Model did not failover to {system_setting.FALLBACK_MODEL_NAME}!"
    print(f"SUCCESS: Fallback logic intercepts missing keys and resolves to Ollama + {system_setting.FALLBACK_MODEL_NAME} successfully!")

if __name__ == "__main__":
    asyncio.run(test_fallback())
