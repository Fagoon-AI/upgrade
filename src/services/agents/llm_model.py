from src.utils.misc import get_model_card


def get_available_model_list(file_path: str) -> list[str]:
    """
    Retrieves the list of model names from the specified model card YAML file.

    Args:
        file_path (str): Path to the model card YAML file.

    Returns:
        list[str]: A list of model names from all available providers (e.g., Groq, OpenAI, Hugging Face).

    Example:
        If the model card contains models from different providers, the function might return:
        ['LLaMA 3 8B', 'DeepSeek LLaMA 70B', 'Fagoon Nova', 'GPT-4o', 'LLaMA 3.1 8B', 'DeepSeek Coder', 'DeepSeek R1'].
    """
    available_models = []

    # Retrieve the model card data
    data = get_model_card(file_path)

    if not data:
        return available_models

    # Iterate over each provider and their models
    for provider in data:
        provider_data = data[provider]
        if "models" in provider_data:
            for model in provider_data["models"]:
                available_models.append(model["name"])

    return available_models
