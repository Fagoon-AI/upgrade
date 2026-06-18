import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict


# ============================================================
# CONFIGURATION
# ============================================================

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_NAME_LENGTH = 255


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class LoginRequest(BaseModel):
    """Schema for login request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PASSWORD_LENGTH,
        description="User password"
    )
    remember_me: bool = Field(
        default=False,
        description="Keep user logged in for extended period"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalizes email to lowercase."""
        return v.lower().strip()


class UserCreate(BaseModel):
    """Schema for user registration."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description="User password (min 8 characters)"
    )
    full_name: Optional[str] = Field(
        default=None,
        max_length=MAX_NAME_LENGTH,
        description="User's full name"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalizes email to lowercase."""
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validates password strength."""
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

        # Check for at least one letter and one number
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)

        if not has_letter:
            raise ValueError("Password must contain at least one letter")

        if not has_digit:
            raise ValueError("Password must contain at least one number")

        return v

    @field_validator("full_name")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizes full name."""
        if not v:
            return None

        v = v.strip()

        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)

        return v if v else None


class PasswordChangeRequest(BaseModel):
    """Schema for password change."""
    current_password: str = Field(
        ...,
        min_length=1,
        description="Current password"
    )
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description="New password"
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validates new password strength."""
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)

        if not has_letter or not has_digit:
            raise ValueError("Password must contain letters and numbers")

        return v


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr = Field(..., description="Account email address")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalizes email."""
        return v.lower().strip()


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""
    token: str = Field(..., min_length=1, description="Reset token")
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description="New password"
    )


class RefreshTokenRequest(BaseModel):
    """Schema for token refresh."""
    refresh_token: Optional[str] = Field(
        default=None,
        description="Refresh token (optional if in cookie)"
    )


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class UserResponseData(BaseModel):
    """Schema for user data in responses."""
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user) -> "UserResponseData":
        """Creates response from user model."""
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            last_login=user.last_login
        )


class TokenData(BaseModel):
    """Schema for token data."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token expiration in seconds")


class LoginResponseData(BaseModel):
    """Schema for login response."""
    user: UserResponseData
    tokens: TokenData
    expires_in: int = Field(description="Token expiration in seconds")


class AuthStatusResponse(BaseModel):
    """Schema for authentication status response."""
    is_authenticated: bool
    user: Optional[UserResponseData] = None


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Schema for simple message response."""
    message: str
    success: bool = True