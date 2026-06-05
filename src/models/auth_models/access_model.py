from pydantic import BaseModel, Field
from typing import List, Any, Dict, Optional
from src.models.auth_models.user_model import PyObjectId

class AccessInDB(BaseModel):
    """
    Model for Access documents stored in MongoDB.
    Represents granular permissions for a user across platforms/features.
    """
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId = Field(..., alias="userId") # Link to User model _id
    access: List[Dict[str, Any]] = [] # Example: [{"platform": "fagoon.ai", "permissions": ["read", "write"]}]

    class Config:
        populate_by_name = True
        arbitrary_types_allowed=True,
        json_encoders = {PyObjectId: str}