import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, String, Index, Boolean, text

if TYPE_CHECKING:
    from src.models.sql.workflow.user import User


# Supported providers
SUPPORTED_PROVIDERS = {
    "GOOGLE",
    "GMAIL_OAUTH",
    "OPENAI",
    "ANTHROPIC",
    "MISTRAL",
    "PERPLEXITY",
    "SUPABASE",
    "SLACK",
    "GITHUB",
    "STRIPE",
    "BROWSERLESS",
    "CUSTOM"
}


class Connection(SQLModel, table=True):
    """
    Secure connection/credential storage model.

    Features:
    - UUID primary key
    - User ownership
    - Provider type validation
    - Encrypted credentials (Fernet)
    - Usage tracking
    - Audit timestamps

    Security:
    - Credentials stored encrypted at rest
    - Never logged or exposed in API responses
    - Provider-specific validation

    Indexes:
    - Primary key on id
    - Foreign key index on user_id
    - Index on provider for filtering
    - Composite index for user queries
    """

    __tablename__ = "connection"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique connection identifier"
    )

    # Ownership
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        index=True,
        description="Owner user ID"
    )

    # Connection info
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="User-friendly connection name"
    )

    provider: str = Field(
        sa_column=Column(String(50), nullable=False, index=True),
        description="Provider type (GOOGLE, OPENAI, etc.)"
    )

    # Encrypted credentials
    encrypted_credentials: str = Field(
        sa_column=Column(String, nullable=False),
        description="Fernet-encrypted credentials JSON"
    )

    # Status
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True),
        description="Connection active status"
    )

    # Usage tracking
    last_used_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last successful usage timestamp"
    )

    use_count: int = Field(
        default=0,
        description="Number of times connection was used"
    )

    # Audit timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=lambda: datetime.now(timezone.utc)
        ),
        description="Last update timestamp"
    )

    # Relationships
    user: "User" = Relationship(back_populates="connections")

    # Table configuration
    __table_args__ = (
        Index("ix_connection_user_provider", "user_id", "provider"),
        Index("ix_connection_user_active", "user_id", "is_active"),
    )

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_oauth(self) -> bool:
        """Checks if this is an OAuth-based connection."""
        return self.provider in {"GMAIL_OAUTH", "GOOGLE", "SLACK", "GITHUB"}

    @property
    def provider_display_name(self) -> str:
        """Gets human-readable provider name."""
        provider_names = {
            "GOOGLE": "Google",
            "GMAIL_OAUTH": "Gmail (OAuth)",
            "OPENAI": "OpenAI",
            "ANTHROPIC": "Anthropic",
            "MISTRAL": "Mistral AI",
            "PERPLEXITY": "Perplexity AI",
            "SUPABASE": "Supabase",
            "SLACK": "Slack",
            "GITHUB": "GitHub",
            "STRIPE": "Stripe",
            "BROWSERLESS": "Browserless",
            "CUSTOM": "Custom"
        }
        return provider_names.get(self.provider, self.provider)

    # ============================================================
    # METHODS
    # ============================================================

    def record_usage(self) -> None:
        """Records that connection was used."""
        self.last_used_at = datetime.now(timezone.utc)
        self.use_count = (self.use_count or 0) + 1

    def deactivate(self) -> None:
        """Deactivates the connection."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def activate(self) -> None:
        """Activates the connection."""
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self, mask_credentials: bool = True) -> Dict[str, Any]:
        """
        Converts connection to dictionary.

        Args:
            mask_credentials: If True, excludes encrypted credentials

        Returns:
            Dictionary representation (never includes raw credentials)
        """
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "provider": self.provider,
            "provider_display_name": self.provider_display_name,
            "is_active": self.is_active,
            "is_oauth": self.is_oauth,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # Never expose credentials in dictionary form
        # Even if mask_credentials is False, we don't include encrypted_credentials

        return data

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Converts to minimal public dictionary.

        Returns:
            Minimal dictionary for listings
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "provider": self.provider,
            "provider_display_name": self.provider_display_name,
            "is_active": self.is_active,
        }

    @classmethod
    def validate_provider(cls, provider: str) -> bool:
        """
        Validates provider type.

        Args:
            provider: Provider type string

        Returns:
            True if valid provider
        """
        return provider.upper() in SUPPORTED_PROVIDERS

    def __repr__(self) -> str:
        return f"<Connection {self.name} ({self.provider})>"

    def __str__(self) -> str:
        return f"{self.name} ({self.provider_display_name})"