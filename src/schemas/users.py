from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field

from typing import Optional


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic validation."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


class UserPreference(BaseModel):
    id: PyObjectId = Field(alias="_id")
    user: PyObjectId
    response_tone: str = Field(alias="responseTone")
    theme: str = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    version: int = Field(alias="__v")
    bio: str = None
    location: str = None
    nickname: str = None
    role: str = None
    system_prompt: str = Field(default=None, alias="systemPrompt")

    class Config:
        populate_by_name: True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Preference(BaseModel):
    tone: Optional[str] = None
    bio: Optional[str] = None
    nickname: Optional[str] = None
    role: Optional[str] = None
    system_prompt: Optional[str] = None
