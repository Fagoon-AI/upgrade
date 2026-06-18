import asyncio
from src.services.map_model_provider import initialize_model_registry, MODEL_REGISTRY
from src.core.settings import system_setting

async def main():
    print("Initial MODEL_REGISTRY:")
    for model_id, provider in list(MODEL_REGISTRY.items())[:10]:
        print(f"  {model_id}: {provider}")
    print(f"  ... total {len(MODEL_REGISTRY)} models")

    print("\nInitializing dynamic model discovery...")
    # Print what API keys are configured (masked)
    print(f"OpenAI Key set: {bool(system_setting.OPENAI_API_KEY)}")
    print(f"Groq Key set: {bool(system_setting.GROQ_API_KEY)}")
    print(f"Gemini Key set: {bool(system_setting.GEMINI_API_KEY)}")
    print(f"Anthropic Key set: {bool(system_setting.ANTHROPIC_API_KEY)}")

    await initialize_model_registry()

    print("\nUpdated MODEL_REGISTRY after discovery:")
    # Group by provider for clearer output
    by_provider = {}
    for model_id, provider in MODEL_REGISTRY.items():
        by_provider.setdefault(provider, []).append(model_id)

    for provider, models in by_provider.items():
        print(f"\nProvider: {provider} ({len(models)} models)")
        # Show first 15 models
        for m in sorted(models)[:15]:
            print(f"  - {m}")
        if len(models) > 15:
            print("  - ...")

    print(f"\nTotal models in registry: {len(MODEL_REGISTRY)}")

if __name__ == "__main__":
    asyncio.run(main())
