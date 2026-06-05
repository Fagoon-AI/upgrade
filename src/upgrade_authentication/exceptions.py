from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.utils.upgrade_auth.app_error import AppError

async def app_error_handler(request: Request, exc: AppError):
    """
    Handles custom AppError exceptions, returning a JSON response.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "fail", "message": exc.message},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handles Pydantic validation errors, returning a more readable JSON response.
    """
    errors = []
    for error in exc.errors():
        loc = ".".join(map(str, error["loc"]))
        errors.append({"field": loc, "message": error["msg"]})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "fail",
            "message": "Validation Error",
            "errors": errors,
            "data": errors
        },
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """
    Handles all other uncaught exceptions. For production, avoid exposing
    detailed error messages for internal server errors.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "Something went very wrong!"},
    )