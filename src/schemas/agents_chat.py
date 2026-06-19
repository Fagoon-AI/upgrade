from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class CreateAgentChatInputRequest(BaseModel):
    user_id: str
    agent_id: str


class AgentChatResponseModel(BaseModel):
    conversation_id: str


# class AgentCustomProfile(BaseModel):
#     system_prompt: Optional[str] = None
#     preferred_tools: Optional[str] = None


# class LLMModelConfiguration(BaseModel):
#     model: Optional[str] = None
#     temperature: Optional[float] = None
#     max_tokens: Optional[int] = None


# class UserMetadata(BaseModel):
#     region: Optional[str] = None
#     country: Optional[str] = None
#     city: Optional[str] = None
#     country_code: Optional[str] = None
#     timezone: Optional[str] = None


class AgentChatInputRequest(BaseModel):
    conversation_id: str
    agent_id: str
    message: str
    file_data: Optional[str] = Field(default=None, description="Base64 encoded file content")
    file_name: Optional[str] = Field(default=None, description="Name of the uploaded file")


# class AgentChatInputRequest1(BaseModel):
#     user_id: str
#     agent_id: str
#     messages: List[Dict[str, Any]]
#     custom_profile: AgentCustomProfile
#     llm_model_config: LLMModelConfiguration
#     metadata: UserMetadata


class EventType(str, Enum):
    TOOL_SELECTION = "tool_selection"
    ERROR = "error"
    STATUS = "status"
    IMAGE = "image"
    VIDEO = "video"
    LLM_RESPONSE = "llm_response"


class ChatHistoryResponse(BaseModel):
    id: str = Field(..., alias="conversation_id")
    title: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={datetime: lambda dt: dt.isoformat()},
    )


class TitleGenerationInputRequest(BaseModel):
    user_id: str
    conversation_id: str
