from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from pathlib import Path
from typing import Any, Dict, Literal, List, Optional, Union


class ResponseModel(BaseModel):
    status: Literal["success", "fail"]
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class SuccessResponse(ResponseModel):
    data: Dict[str, Any] = None


class FailureResponse(ResponseModel):
    message: str


class ImageFormat(Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"

    @staticmethod
    def from_path(path: Union[str, Path]):
        ext = Path(path).suffix.lower().strip(".")
        try:
            return ImageFormat(ext)
        except ValueError:
            raise ValueError(f"Unsupported image format: .{ext}")


# class ChatInsertModel(BaseModel):
#     id: str = Field(alias="conversation_id")
#     role: str
#     tool_selection: Dict[str, Any] = None
#     message: str
#     metadata: List[Dict[str, Any]] = None
#     images: Any = None
#     created_at: datetime = Field(
#         alias="createdAt", default_factory=lambda: datetime.now(timezone.utc)
#     )
#     updated_at: datetime = Field(
#         alias="updatedAt", default_factory=lambda: datetime.now(timezone.utc)
#     )
#
#     class Config:
#         json_encoders = {datetime: lambda v: v.isoformat()}
#         validate_by_name = True


class ConversationRoleEnum(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# class UpgradeChatInsertModel(ChatInsertModel):
#     id: str = Field(alias="uuid")
#
#     class Config:
#         validate_by_name = True

class UpgradeChatInsertModel(BaseModel):
    uuid: str
    role: str
    message: str
    tool_selection: Optional[Dict] = None
    images: Optional[Dict] = None
    metadata: Optional[List[Dict]] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True,
    )



# class AgentChatInsertModel(ChatInsertModel):
#     pass

class AgentChatInsertModel(BaseModel):
    uuid: str
    role: str
    message: str
    tool_selection: Optional[Dict] = None
    images: Optional[Dict] = None
    metadata: Optional[List[Dict]] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda dt: dt.isoformat()},
        arbitrary_types_allowed=True,
    )