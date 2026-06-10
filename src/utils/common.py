from bson import ObjectId
import io
import json
import nanoid
import time
import uuid
from functools import wraps
from loguru import logger
from pathlib import Path
from PIL import Image
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar
from typing import AsyncGenerator, NewType, Union

from urllib.parse import urlparse

from src.schemas.agents_chat import EventType
from src.schemas.common import ImageFormat


# Define generic type variables for return type and parameters
R = TypeVar("R")
P = ParamSpec("P")
UniqueId = NewType("UniqueId", str)


def async_time_execution(
    func: Callable[..., Coroutine[Any, Any, R]],
) -> Callable[..., Coroutine[Any, Any, R]]:
    @wraps(func)
    async def wrapper(*args, **kwargs) -> R:
        start_time = time.time()
        logger.debug(f"[START] {func.__name__}")

        result = await func(*args, **kwargs)

        execution_time = time.time() - start_time
        logger.debug(
            f"[END] {func.__name__} | result={result!r} | duration={execution_time:.4f}s"
        )

        return result

    return wrapper


def generate_id() -> UniqueId:
    while True:
        new_id = nanoid.generate(size=10)
        if "-" not in (new_id[0], new_id[-1]) and "_" not in new_id:
            return UniqueId(new_id)


def is_valid_url(url: str) -> bool:
    try:
        if not url.startswith("https://"):
            raise ValueError("URL must start with 'https://'")

        # Parse the URL
        result = urlparse(url)
        return all([result.scheme, result.netloc])

    except ValueError:
        return False


def flatten_json(nested_json, parent_key="", sep="."):
    """
    Flattens a nested JSON object into a single level with dot notation keys.

    Args:
    - nested_json: The JSON object to be flattened (could be a dictionary or list).
    - parent_key: The base key (used for recursion).
    - sep: The separator used for dot notation (default is '.').

    Returns:
    - A flattened dictionary with keys in dot notation.
    """
    items = {}

    for k, v in nested_json.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            # Recursively flatten dictionaries
            items.update(flatten_json(v, new_key, sep))

        elif isinstance(v, list):
            # Flatten lists by iterating through them
            for i, el in enumerate(v):
                items.update(flatten_json({i: el}, new_key, sep))

        else:
            # Base case: add the value if it's not a dictionary or list
            items[new_key] = v

    return items

def generate_uuid():
    return str(uuid.uuid4())


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as e:
        raise ValueError(f"Invalid ObjectId value: {value}") from e


async def send_event_data(
    event_type: EventType, data: Union[str, dict]
) -> AsyncGenerator[str, None]:
    payload = json.dumps(
        {"type": event_type.value, "data": data}, ensure_ascii=False
    )
    yield f"data: {payload}\n\n"


def save_image(
    image: Image.Image, path: Union[str, Path], format_: ImageFormat
) -> Path:
    path = Path(path).with_suffix(f".{format_.value}")
    try:
        image.save(path, format=format_.name)
        return path
    except Exception as e:
        raise IOError(f"Failed to save image to: {path}") from e


def read_image(path: Union[str, Path]) -> Image.Image:
    """Read image from given path"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    try:
        return Image.open(path)
    except Exception as e:
        raise IOError(f"Failed to read image: {path}") from e


def get_bytes_stream(file_bytes: bytes) -> io.BytesIO:
    """Convert file bytes into in-memory buffer"""
    if not file_bytes:
        raise ValueError("file_bytes must not be empty")
    return io.BytesIO(file_bytes)


# NEW FUNCTIONS
async def send_sse_event(event_type: str, data: Any) -> AsyncGenerator[str, None]:
    """
    Formats data as a Server-Sent Event (SSE) string.

    Args:
        event_type (str): The type of the event (e.g., 'tool_selection', 'token', 'error').
        data (Any): The data payload for the event.

    Yields:
        str: The formatted SSE message string.
    """
    # This structure matches the user's requirement for a nested JSON object.
    payload = {"type": event_type, "data": data}
    yield f"data: {json.dumps(payload)}\n\n"

async def send_sse_token(token: str) -> AsyncGenerator[str, None]:
    """
    Formats a single token for streaming as a Server-Sent Event (SSE).
    This is for the LLM's character-by-character output.
    """
    payload = {"token": token}
    yield f"data: {json.dumps(payload)}\n\n"
