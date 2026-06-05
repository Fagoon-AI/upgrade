from pydantic import BaseModel
from typing import Any, Dict, Literal, Optional


class BaseResponse(BaseModel):
    status: Literal["success", "fail"]
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseResponse):
    status: Literal["success"]


class ErrorResponse(BaseResponse):
    status: Literal["fail"]
    error_details: Optional[str] = None
