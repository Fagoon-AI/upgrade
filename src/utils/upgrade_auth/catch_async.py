from functools import wraps
from loguru import logger
from fastapi import Request
from src.utils.upgrade_auth.app_error import AppError

def catch_async(func):
    """
    Decorator to catch exceptions from async functions and log errors
    before re-raising them as AppError.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppError as e:
            logger.warning(f"AppError in {func.__name__}: {e.message}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise AppError("An unexpected error occurred.", status_code=500)
    return wrapper
