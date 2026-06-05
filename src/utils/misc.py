import re
import random
import string
import yaml
import json
from PIL import Image
from io import BytesIO
from fastapi import Request, HTTPException, status
from pydantic import BaseModel, ValidationError

from typing import Any, Optional, Tuple, List, Type, TypeVar, Dict


T = TypeVar("T", bound=BaseModel)

async def validate_request_body(request: Request, model_cls: Type[T]) -> T:
    """
    Parses and validates the JSON body of a request against a Pydantic model.

    Args:
        request: The FastAPI Request object.
        model_cls: The Pydantic model class to validate against.

    Returns:
        An instance of the Pydantic model if validation is successful.

    Raises:
        HTTPException: If the request body is invalid JSON or fails validation.
    """
    try:
        body = await request.json()
        return model_cls.model_validate(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format.",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(),
        )


def convert_samples_to_bytes(samples, sample_rate) -> bytes:
    """Convert speech samples to bytes"""
    import soundfile as sf

    byte_io = BytesIO()
    sf.write(byte_io, samples, sample_rate, format="WAV")
    byte_io.seek(0)
    return byte_io.read()


def generate_unique_id(length: int = 6) -> str:
    """Generate a short random alphanumeric string."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def clean_string(text):
    """
    This function takes in a string and performs a series of text cleaning operations.

    Args:
        text (str): The text to be cleaned. This is expected to be a string.

    Returns:
        cleaned_text (str): The cleaned text after all the cleaning operations
        have been performed.
    """
    # Stripping and reducing multiple spaces to single:
    cleaned_text = re.sub(r"\s+", " ", text.strip())

    # Removing backslashes:
    cleaned_text = cleaned_text.replace("\\", "")

    # Replacing hash characters:
    cleaned_text = cleaned_text.replace("#", " ")

    # Eliminating consecutive non-alphanumeric characters:
    # This regex identifies consecutive non-alphanumeric characters (i.e., not
    # a word character [a-zA-Z0-9_] and not a whitespace) in the string
    # and replaces each group of such characters with a single occurrence of
    # that character.
    # For example, "!!! hello !!!" would become "! hello !".
    cleaned_text = re.sub(r"([^\w\s])\1*", r"\1", cleaned_text)

    return cleaned_text


def convert_pil_image_to_bytes(image: Image, format: str = "PNG") -> bytes:
    """Converts a PIL Image to raw bytes in the given format."""
    buffer = BytesIO()
    image.save(buffer, format=format)
    buffer.seek(0)
    return buffer.read()


def read_yml_file(file_path: str):
    with open(file_path, "r") as f:
        return yaml.safe_load(f.read())


def get_model_card(file_path: str) -> Optional[Any]:
    model_card = read_yml_file(file_path)
    return model_card if model_card is not None else None


def get_model_id_and_service(path, model_name) -> Tuple[Optional[str], Optional[str]]:
    data = get_model_card(path)

    if data is None:
        return None, None

    for service_key in data:
        service = data[service_key]
        models = service.get("models", [])
        for model_entry in models:
            # Changed from model_entry.get("name") to model_entry.get("id")
            if model_entry.get("id") == model_name:
                model_id = model_entry.get("id")
                return model_id, service_key

    return None, None

def get_user_latest_query(history: List[Dict]) -> str:
    """
    Extracts the latest user query from the conversation history.
    Handles multi-modal content by extracting text from a list of content blocks.
    """
    if not history:
        return ""

    latest_user_message = next(
        (msg for msg in reversed(history) if msg.get("role") == "user"), None
    )

    if not latest_user_message or not latest_user_message.get("content"):
        return ""

    content = latest_user_message["content"]

    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = [
            item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
        ]
        return " ".join(text_parts).strip()

    return ""


def is_none_or_empty(item):
    return item is None or (hasattr(item, "__iter__") and len(item) == 0) or item == ""


def is_query_empty(query: str) -> bool:
    return is_none_or_empty(query.strip())


# TODO: Remove this, map in previous enum itself
def map_conversation_command(commands: List[str]) -> str:
    mapping = {
        "general": "General",
        "web_search": "Web Search",
        "image_generation": "Image Generation",
        "mermaid_diagram": "Mermaid Diagram",
        "deep_research": "Deep Research",
        "summarization": "Summarization",
        "note_taking": "Note Taking",
    }

    display_names = [
        mapping.get(cmd.lower()) for cmd in commands if cmd.lower() in mapping
    ]

    return ", ".join(display_names)


def sanitize_chat(chat_history):
    from bson import ObjectId
    from datetime import datetime

    sanitized = []
    for chat in chat_history:
        chat_dict = dict(chat)
        chat_dict.pop("_id", None)  # Remove _id
        # Convert ObjectId or datetime if needed
        for key, value in chat_dict.items():
            if isinstance(value, ObjectId):
                chat_dict[key] = str(value)
            elif isinstance(value, datetime):
                chat_dict[key] = value.isoformat()
        sanitized.append(chat_dict)
    return sanitized


def is_simple_conversational_query(query: str) -> bool:
    """
    Checks if a query is a simple greeting or common phrase that doesn't require a tool.
    """
    query = query.lower().strip()
    greetings = ["hello", "hi", "hey", "how are you", "what's up", "good morning", "good afternoon", "good evening"]
    common_phrases = ["thanks", "thank you", "ok", "okay", "cool", "sounds good", "got it"]

    if query in greetings or query in common_phrases:
        return True
    # A simple length check can also weed out queries that are too short to need a tool.
    if len(query.split()) < 3:
        return True
    return False