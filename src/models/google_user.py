from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """
    Represents a user in your system. This is a minimal example.
    You might integrate with your existing authentication system here.
    For this project, we'll assume a user is created when they first
    authenticate via Google.
    """

    id: str = Field(
        alias="_id",
        default_factory=lambda: str(datetime.now().timestamp()).replace(".", ""),
    )
    google_id: Optional[str] = Field(
        None, description="The unique Google ID for the user."
    )
    email: str = Field(..., description="User's email, typically from Google.")
    name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
