from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class AgentProfile(BaseModel):
    agent_name: Optional[str] = Field(default=None, description="The name of the agent")
    description: Optional[str] = Field(
        default=None, description="A short description of the agent"
    )
    image: Optional[str] = Field(
        default=None, description="URL or path to the agent's image"
    )


class AIModelSetting(BaseModel):
    llm_model: str = Field(
        default=..., description="The name of the language model to use"
    )
    temperature: Optional[float] = Field(
        default=0.1, description="Sampling temperature for response randomness"
    )
    top_p: Optional[float] = Field(
        default=0.1, description="Top-p sampling probability for the model"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Numbers of token to generate during the inference time",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for the selected LLM provider",
    )


class KnowledgeBase(BaseModel):
    uploaded_files: Optional[List[str]] = Field(
        default=None, description="List of file paths or names for the knowledge base"
    )
    urls: Optional[List[str]] = Field(
        default=None, description="List of URLs to include in the knowledge base"
    )


class AgentDefaultModel(BaseModel):
    user_id: Optional[str] = Field(
        default=None, description="Unique identifier for the user, if available"
    )
    agent_id: Optional[str] = Field(
        default=None, description="Unique ID assigned for the agent"
    )
    profile: Optional[AgentProfile] = Field(
        default=None, description="Profile details of the agent"
    )
    system_prompt: Optional[str] = Field(
        default=None, description="The system-level prompt defining agent behavior"
    )
    model_settings: Optional[AIModelSetting] = Field(
        default=None, description="Settings for the AI model behavior"
    )
    knowledge_base: Optional[KnowledgeBase] = Field(
        default=None, description="Knowledge base resources for the agent"
    )

    tools: Optional[List[str]] = Field(
        default=None,
        description="List of tools available to the agent, e.g., WebSearchTool, ResearchTool, ImageGenerationTool",
    )

    ingestion_status: Optional[str] = "pending_ingestion"

    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the agent was created",
    )
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the agent was last updated",
    )

    class Config:
        # Ensure that the created_at and updated_at fields are serialized correctly
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    @property
    def name(self) -> Optional[str]:
        if self.profile and self.profile.agent_name:
            return self.profile.agent_name
        return None

    @property
    def description(self) -> Optional[str]:
        if self.profile:
            return self.profile.description
        return None

    @property
    def instructions(self) -> Optional[str]:
        return self.system_prompt


class ListAgentModel(BaseModel):
    agent_id: Optional[str] = Field(
        default=None, description="Unique ID assigned for the agent"
    )
    name: Optional[str] = Field(default=None, description="The name of the agent")
    description: Optional[str] = Field(
        default=None, description="A short description of the agent"
    )
    image: Optional[str] = Field(
        default=None, description="URL or path to the agent's image"
    )

class AgentUpdateModel(BaseModel):
    name: Optional[str] = None
    instructions: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    llm_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    model_settings: Optional[AIModelSetting] = None
    knowledge_base: Optional[KnowledgeBase] = None
    tools: Optional[List[str]] = None
    profile: Optional[AgentProfile] = None
    system_prompt: Optional[str] = None
    
    
class ChatTitleRequest(BaseModel):
    conversation_id: str
    user_id: str
