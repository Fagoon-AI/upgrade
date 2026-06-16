from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal, List


class BaseLLMConfig(BaseModel):
    model: str
    max_tokens: Optional[int] = None
    provider: Literal["openai", "hugging_face", "groq", "anthropic", "localhost", "gemini"]
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = 0.1
    api_key: Optional[str] = None


class LLMModelConfigCreate(BaseModel):
    name: str
    provider: Literal["openai", "hugging_face", "groq", "anthropic", "localhost", "gemini"]
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    features: Optional[List[Literal["chat", "agents", "workflow"]]] = Field(default_factory=list)
    agent_ids: Optional[List[str]] = Field(default_factory=list)
    workflow_ids: Optional[List[str]] = Field(default_factory=list)


class LLMModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[Literal["openai", "hugging_face", "groq", "anthropic", "localhost", "gemini"]]
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    features: Optional[List[Literal["chat", "agents", "workflow"]]] = None
    agent_ids: Optional[List[str]] = None
    workflow_ids: Optional[List[str]] = None


class LLMModelConfigResponse(BaseModel):
    id: str
    name: str
    provider: str
    model_id: Optional[str] = None
    masked_api_key: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    agent_ids: List[str] = Field(default_factory=list)
    workflow_ids: List[str] = Field(default_factory=list)
    is_enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
