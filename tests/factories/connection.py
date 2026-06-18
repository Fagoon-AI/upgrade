"""
Connection model factory for test data generation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import factory
from faker import Faker

from src.models.sql.workflow.connection import Connection, SUPPORTED_PROVIDERS

fake = Faker()


class ConnectionFactory(factory.Factory):
    """
    Factory for creating Connection instances.

    Usage:
        # Create with defaults (OpenAI)
        connection = ConnectionFactory()

        # Create for specific provider
        connection = ConnectionFactory.create_for_provider("ANTHROPIC")

        # Create OAuth connection
        connection = ConnectionFactory.create_oauth_connection(user_id=user.id)
    """

    class Meta:
        model = Connection

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    user_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    name: str = factory.LazyFunction(lambda: f"Connection {fake.word().title()}")
    provider: str = "OPENAI"
    encrypted_credentials: str = factory.LazyFunction(
        lambda: f"encrypted_{fake.uuid4()}"
    )
    is_active: bool = True
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    created_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    def create_for_provider(cls, provider: str, **kwargs) -> Connection:
        """
        Create connection for specific provider.

        Args:
            provider: Provider name (OPENAI, ANTHROPIC, etc.)
            **kwargs: Additional fields

        Raises:
            ValueError: If provider is not supported
        """
        if provider.upper() not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")

        provider_names = {
            "OPENAI": "OpenAI API Key",
            "ANTHROPIC": "Anthropic API Key",
            "MISTRAL": "Mistral API Key",
            "PERPLEXITY": "Perplexity API Key",
            "GOOGLE": "Google Service Account",
            "GMAIL_OAUTH": "Gmail OAuth",
            "SLACK": "Slack Bot Token",
            "GITHUB": "GitHub App",
            "STRIPE": "Stripe API Key",
            "BROWSERLESS": "Browserless API Key",
            "SUPABASE": "Supabase Connection",
            "CUSTOM": "Custom API",
        }

        return cls(
            provider=provider.upper(),
            name=provider_names.get(provider.upper(), f"{provider} Connection"),
            **kwargs,
        )

    @classmethod
    def create_openai(cls, **kwargs) -> Connection:
        """Create OpenAI connection."""
        return cls.create_for_provider("OPENAI", **kwargs)

    @classmethod
    def create_anthropic(cls, **kwargs) -> Connection:
        """Create Anthropic connection."""
        return cls.create_for_provider("ANTHROPIC", **kwargs)

    @classmethod
    def create_google(cls, **kwargs) -> Connection:
        """Create Google service account connection."""
        return cls.create_for_provider("GOOGLE", **kwargs)

    @classmethod
    def create_gmail_oauth(cls, **kwargs) -> Connection:
        """Create Gmail OAuth connection."""
        return cls.create_for_provider("GMAIL_OAUTH", **kwargs)

    @classmethod
    def create_oauth_connection(cls, provider: str = "GMAIL_OAUTH", **kwargs) -> Connection:
        """Create an OAuth-based connection."""
        oauth_providers = {"GMAIL_OAUTH", "GOOGLE", "SLACK", "GITHUB"}
        if provider.upper() not in oauth_providers:
            raise ValueError(f"Not an OAuth provider: {provider}")
        return cls.create_for_provider(provider, **kwargs)

    @classmethod
    def create_inactive(cls, **kwargs) -> Connection:
        """Create an inactive connection."""
        return cls(is_active=False, **kwargs)

    @classmethod
    def create_with_usage(cls, use_count: int = 10, **kwargs) -> Connection:
        """Create a connection with usage history."""
        return cls(
            use_count=use_count,
            last_used_at=datetime.now(timezone.utc),
            **kwargs,
        )

    @classmethod
    def create_all_providers(cls, user_id: uuid.UUID) -> list[Connection]:
        """
        Create one connection for each supported provider.

        Useful for testing provider-specific logic.

        Args:
            user_id: Owner user ID

        Returns:
            List of Connection instances
        """
        return [
            cls.create_for_provider(provider, user_id=user_id)
            for provider in SUPPORTED_PROVIDERS
        ]


class ConnectionCreateDataFactory(factory.Factory):
    """Factory for connection creation request data."""

    class Meta:
        model = dict

    name: str = factory.LazyFunction(lambda: f"New Connection {fake.word()}")
    provider: str = "OPENAI"
    credentials: Dict[str, Any] = factory.LazyFunction(
        lambda: {"api_key": f"sk-test-{fake.uuid4()}"}
    )

    @classmethod
    def for_openai(cls, api_key: Optional[str] = None) -> dict:
        """Create OpenAI connection data."""
        return cls(
            name="OpenAI Connection",
            provider="OPENAI",
            credentials={"api_key": api_key or f"sk-test-{fake.uuid4()}"},
        )

    @classmethod
    def for_anthropic(cls, api_key: Optional[str] = None) -> dict:
        """Create Anthropic connection data."""
        return cls(
            name="Anthropic Connection",
            provider="ANTHROPIC",
            credentials={"api_key": api_key or f"sk-ant-test-{fake.uuid4()}"},
        )

    @classmethod
    def for_gmail_oauth(cls) -> dict:
        """Create Gmail OAuth connection data (requires OAuth flow)."""
        return cls(
            name="Gmail OAuth",
            provider="GMAIL_OAUTH",
            credentials={},  # OAuth credentials set after flow
        )

    @classmethod
    def invalid_provider(cls) -> dict:
        """Create data with invalid provider (for validation tests)."""
        return cls(
            provider="INVALID_PROVIDER",
            credentials={"key": "value"},
        )
