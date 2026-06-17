from pydantic import BaseModel, Field
from typing import Optional


class LLMConfig(BaseModel):
    max_tokens: int = Field(default=..., description="Setup the number of max token")
    model: str = Field(
        default=..., description="Name of the LLM Model used for Response Generation"
    )
    provider: str = Field(default=..., description="Name of the model provider")
    temperature: float = Field(
        default=0.1, description="Control the creativity of the model output"
    )
    top_p: float = Field(
        default=0.1,
        description="control the randomness and diversity of the generated text",
    )


class ChatInputRequest(BaseModel):
    llm_config: LLMConfig = Field(
        ..., description="Configuration for the language model to be used"
    )
    system_prompt: Optional[str] = Field(
        default=None, description="Initial prompt to set the system behavior"
    )
    user_id: Optional[str] = Field(
        default=None, description="Unique identifier for the user"
    )
    user_prompt: Optional[str] = Field(
        ..., description="Prompt message provided by the user"
    )
    feature: Optional[str] = Field(
        default="workflow", description="The feature requesting the completion"
    )
