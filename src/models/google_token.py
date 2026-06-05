from datetime import datetime, timedelta
from typing import Optional, List

from pydantic import BaseModel, Field


class GoogleToken(BaseModel):
    """
    Represents Google OAuth2.0 tokens stored per user.
    """

    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str = Field(
        ..., description="Internal ID of the user associated with this token."
    )
    access_token: str
    refresh_token: Optional[str] = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: str
    client_secret: str
    scopes: List[str]
    token_expiry: datetime = Field(
        ..., description="Timestamp when the access token expires."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # TODO: validate_by_name rename
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}
