from pydantic import BaseModel


class GoogleTokenResponse(BaseModel):
    """
    Schema for the token details returned after successful Google OAuth.
    This is no longer directly returned by the callback, but represents
    the info retrieved by the backend after Google Auth.
    """

    user_id: str
    email: str
    refresh_token_available: bool


class JWTCreds(BaseModel):
    """Schema for the JWT returned to the client."""

    access_token: str
    token_type: str = "bearer"


class GoogleUserDetails(BaseModel):
    google_id: str
    system_user_id: str
