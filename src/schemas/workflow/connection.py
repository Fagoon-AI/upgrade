from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


# ============================================================
# CONFIGURATION
# ============================================================

SUPPORTED_PROVIDERS = {
    "GOOGLE": {
        "display_name": "Google",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": True
    },
    "GMAIL_OAUTH": {
        "display_name": "Gmail (OAuth)",
        "required_fields": [],
        "optional_fields": [],
        "oauth_supported": True
    },
    "OPENAI": {
        "display_name": "OpenAI",
        "required_fields": ["api_key"],
        "optional_fields": ["organization_id"],
        "oauth_supported": False
    },
    "ANTHROPIC": {
        "display_name": "Anthropic",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "MISTRAL": {
        "display_name": "Mistral AI",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "PERPLEXITY": {
        "display_name": "Perplexity AI",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "SUPABASE": {
        "display_name": "Supabase",
        "required_fields": ["project_url", "service_role_key"],
        "optional_fields": ["anon_key"],
        "oauth_supported": False
    },
    "SLACK": {
        "display_name": "Slack",
        "required_fields": [],
        "optional_fields": ["bot_token", "webhook_url"],
        "oauth_supported": True
    },
    "GITHUB": {
        "display_name": "GitHub",
        "required_fields": [],
        "optional_fields": ["access_token"],
        "oauth_supported": True
    },
    "STRIPE": {
        "display_name": "Stripe",
        "required_fields": ["secret_key"],
        "optional_fields": ["publishable_key", "webhook_secret"],
        "oauth_supported": False
    },
    "BROWSERLESS": {
        "display_name": "Browserless",
        "required_fields": ["api_key"],
        "optional_fields": [],
        "oauth_supported": False
    },
    "CUSTOM": {
        "display_name": "Custom",
        "required_fields": [],
        "optional_fields": [],
        "oauth_supported": False
    }
}


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ConnectionCreate(BaseModel):
    """Schema for creating a connection."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Connection name"
    )
    provider: str = Field(
        ...,
        description="Provider type (GOOGLE, OPENAI, etc.)"
    )
    credentials: Dict[str, Any] = Field(
        ...,
        description="Provider credentials"
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validates provider type."""
        v = v.upper().strip()

        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider. Must be one of: {', '.join(SUPPORTED_PROVIDERS.keys())}"
            )

        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Sanitizes connection name."""
        v = v.strip()

        if not v:
            raise ValueError("Connection name cannot be empty")

        return v


class ConnectionUpdate(BaseModel):
    """Schema for updating a connection."""
    name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="New connection name"
    )
    credentials: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated credentials"
    )

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizes connection name."""
        if v is None:
            return None

        v = v.strip()
        return v if v else None


class ConnectionTestRequest(BaseModel):
    """Schema for testing a connection."""
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Test timeout in seconds"
    )


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class ConnectionResponse(BaseModel):
    """Schema for connection response."""
    id: UUID
    name: str
    provider: str
    provider_display_name: str
    is_active: bool = True
    is_oauth: bool = False
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    created_at: datetime
    updated_at: datetime

    # Masked credentials (for display only)
    credentials_preview: Optional[Dict[str, str]] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_connection(
            cls,
            connection,
            include_preview: bool = False
    ) -> "ConnectionResponse":
        """Creates response from connection model."""
        provider_info = SUPPORTED_PROVIDERS.get(connection.provider, {})

        preview = None
        if include_preview:
            # Would need to decrypt and mask credentials
            preview = {"status": "configured"}

        return cls(
            id=connection.id,
            name=connection.name,
            provider=connection.provider,
            provider_display_name=provider_info.get("display_name", connection.provider),
            is_active=connection.is_active,
            is_oauth=provider_info.get("oauth_supported", False),
            last_used_at=connection.last_used_at,
            use_count=connection.use_count,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            credentials_preview=preview
        )


class ConnectionListResponse(BaseModel):
    """Schema for connection list item."""
    id: UUID
    name: str
    provider: str
    provider_display_name: str
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderInfo(BaseModel):
    """Schema for provider information."""
    provider: str
    display_name: str
    required_fields: List[str]
    optional_fields: List[str]
    oauth_supported: bool


class ProviderListResponse(BaseModel):
    """Schema for provider list response."""
    providers: List[ProviderInfo]


class ConnectionTestResponse(BaseModel):
    """Schema for connection test response."""
    success: bool
    message: str
    latency_ms: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


class OAuthUrlResponse(BaseModel):
    """Schema for OAuth URL response."""
    auth_url: str
    state: Optional[str] = None
    expires_in: Optional[int] = None


class OAuthCallbackResponse(BaseModel):
    """Schema for OAuth callback response."""
    connection_id: UUID
    provider: str
    message: str = "Connection created successfully"