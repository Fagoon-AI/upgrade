from typing import Optional

MODEL_REGISTRY: dict[str, str] = {
    "gemini-1.5-flash": "gemini",
    "gemini-1.5-pro": "gemini",
    "gemini-2.0-flash": "gemini",
    "gemini-2.5-flash": "gemini",
    "llama-3.3-70b-versatile": "groq",
    "llama3-8b-8192": "groq",
    "deepseek-r1-distill-llama-70b": "groq",
    # "04-mini": "openai",
    "gpt-3.5-turbo": "openai",
    "gpt-4o": "openai",
    "gpt-4": "openai",
    "o4-mini": "openai",
    "gpt-4o-mini": "openai", # New Added
    "meta-llama/Llama-3.1-8B-Instruct": "hugging_face",
    "deepseek-ai/deepseek-coder-1.3b-instruct": "hugging_face",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": "hugging_face",
    "meta-llama/Llama-3.1-70B-Instruct": "hugging_face",
    "codellama/CodeLlama-34b-Instruct-hf": "hugging_face",
}


def get_model_provider(model_id: str) -> str:
    """
    Look up the provider for a given model ID.

    Args:
        model_id (str): The model's identifier.

    Returns:
        Optional[str]: The provider name if the model is registered; otherwise, None.
    """
    # return MODEL_REGISTRY.get(model_id)
    provider = MODEL_REGISTRY.get(model_id)
    if provider is None:
        raise ValueError(f"No LLM provider found for model ID: '{model_id}'. "
                         "Please add it to MODEL_REGISTRY or use a known model.")
    return provider
