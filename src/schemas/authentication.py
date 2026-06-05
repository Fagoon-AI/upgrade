from pydantic import BaseModel

from typing import Optional, Literal


class TokenData(BaseModel):
    user_id: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    refresh_token: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str

