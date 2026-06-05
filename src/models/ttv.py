from pydantic import BaseModel, Field

from src.models.enum_config import UserType, AvailableTextToVideoProvider

class TTVConfig(BaseModel):
    model_type: AvailableTextToVideoProvider = Field(default=..., description="Type of the model type used")
    temperature: float = Field(default=0.1, description="Control the creativity of the model output")
    api_key: str = Field(default=None, description="API Key for the TTV Client")
    model_name: str = Field(default=None, description="Name of the TTV Model used for Inference Generation")

class TTVInputRequest(BaseModel):
    user_prompt: str
    user_type: UserType
    ttv_config: TTVConfig
