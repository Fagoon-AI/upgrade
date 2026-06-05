from enum import Enum
from pydantic import BaseModel

from typing import Optional


class ResponseEnum(str, Enum):
    SUCCESS = "success"
    FAILED = "fail"


class InputRequestBody(BaseModel):
    query: str


class SupportBotResponseModel(BaseModel):
    status: str
    data: Optional[str] = None
    error_details: Optional[str] = None
