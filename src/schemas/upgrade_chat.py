from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer 
from typing import Any, Dict, List, Optional
from datetime import datetime
from bson import ObjectId
from enum import Enum

from src.schemas.common import UpgradeChatInsertModel


class ChatEventType(Enum):
    START_LLM_RESPONSE = "start_llm_response"
    END_LLM_RESPONSE = "end_llm_response"
    MESSAGE = "message"
    REFERENCES = "references"
    GENERATED_ASSETS = "generated_assets"
    STATUS = "status"
    THOUGHT = "thought"
    METADATA = "metadata"
    USAGE = "usage"
    END_RESPONSE = "end_response"
    TOOL_SELECTION = "tool_selection"
    ERROR = "error"
    IMAGE = "image"
    VIDEO = "video"
    LLM_RESPONSE = "llm_response"
    AUDIO_OUTPUT = "audio_output"


class ConversationAvailableServices(str, Enum):
    DEFAULT = "default"
    IMAGE = "image"
    WEB_SEARCH = "web_search"
    DIAGRAM = "diagram"
    SUMMARIZE = "summarize"


class UpgradeEntrypointInputRequest(BaseModel):
    user_id: str


# class ChatEntrypointModel(BaseModel):
#     id: Optional[ObjectId] = Field(default=None)
#     uuid: str
#     user: ObjectId
#     title: str = None
#
#     created_at: datetime = Field(alias="createdAt")
#     updated_at: datetime = Field(alias="updatedAt")
#
#     @field_validator("id", "user", mode="before")
#     def validate_object_id(cls, value):
#         if isinstance(value, ObjectId):
#             return value
#         if isinstance(value, str):
#             try:
#                 return ObjectId(value)
#             except Exception:
#                 raise ValueError("Invalid ObjectId format")
#         raise TypeError("Expected ObjectId or string")
#
#     @field_serializer("id", "user")
#     def serialize_object_id(self, value: ObjectId, _info):
#         return str(value)
#
#     model_config = {
#         "arbitrary_types_allowed": True,
#         "from_attributes": True,
#         "populate_by_name": True
#     }

class ChatEntrypointModel(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    uuid: str
    user: Optional[ObjectId] = None
    title: Optional[str] = None

    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @field_validator("id", "user", mode="before")
    def validate_object_id(cls, value):
        if value is None:
            return None
        if isinstance(value, ObjectId):
            return value
        if isinstance(value, str):
            try:
                return ObjectId(value)
            except Exception:
                raise ValueError("Invalid ObjectId format")
        raise TypeError("Expected ObjectId or string, but got a different type")

    @field_serializer("id", "user")
    def serialize_object_id(self, value: ObjectId, _info):
        if value is None:
            return None
        return str(value)

    model_config = {
        "arbitrary_types_allowed": True,
        "from_attributes": True,
        "populate_by_name": True,
    }


class ChatHistory(BaseModel):
    id: str = Field(..., alias="uuid")
    title: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda dt: dt.isoformat()},
    )


# class ConversationResponse(BaseModel):
#     title: str = None
#     messages: List[Dict[str, Any]]


class ConversationResponse(BaseModel):
    uuid: str
    title: str = ""
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    messages: List[UpgradeChatInsertModel]

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda dt: dt.isoformat()},
    )