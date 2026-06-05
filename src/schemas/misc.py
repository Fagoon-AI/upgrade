from fastapi import Request, HTTPException
from pydantic import ValidationError
from typing import Type, TypeVar
import json

T = TypeVar("T")


async def validate_request_body(request: Request, model: Type[T]) -> T:
    """
    Reads, parses, and validates the JSON body of a FastAPI Request against a given Pydantic model.

    Args:
        request (Request): The FastAPI request object.
        model (Type[T]): A Pydantic model class to validate the input against.

    Returns:
        T: An instance of the validated Pydantic model.

    Raises:
        HTTPException:
            - 400 if the body is not valid JSON or any unexpected error occurs.
            - 422 if the JSON is valid but fails Pydantic validation.
    """
    try:
        raw_body = await request.body()
        body = json.loads(raw_body)
        return model(**body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unexpected error: {str(e)}")
