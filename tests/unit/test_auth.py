"""
Unit tests for authentication functionality.

Tests cover:
- Password hashing and verification
- Token creation and validation
- User model operations
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from src.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_access_token,
    validate_refresh_token,
    TokenType,
    generate_api_key,
    hash_api_key,
)
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.execution import WorkflowExecution
from src.models.sql.workflow.schedule import WorkflowSchedule
from src.models.sql.workflow.connection import Connection


class TestPasswordHashing:
    """Tests for password hashing operations."""

    def test_hash_password(self):
        """Password hashing should produce different hash each time."""
        password = "TestPassword123!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != password
        assert hash2 != password
        assert hash1 != hash2  # Different salts

    def test_verify_correct_password(self):
        """Correct password should verify successfully."""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_incorrect_password(self):
        """Incorrect password should fail verification."""
        password = "TestPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_empty_password(self):
        """Empty password should fail verification."""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password("", hashed) is False

    def test_hash_empty_password(self):
        """Empty password can still be hashed (validation elsewhere)."""
        hashed = get_password_hash("")
        assert hashed is not None
        assert len(hashed) > 0


class TestTokenCreation:
    """Tests for JWT token creation."""

    def test_create_access_token(self):
        """Access token should be created with correct claims."""
        user_id = uuid4()
        token = create_access_token(user_id)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_expiry(self):
        """Access token should respect custom expiry."""
        user_id = uuid4()
        custom_expiry = timedelta(minutes=15)
        token = create_access_token(user_id, expires_delta=custom_expiry)

        payload, error = decode_token(token)
        assert error is None
        assert payload is not None
        # Token should expire roughly in 15 minutes
        time_diff = payload.exp - datetime.now(timezone.utc)
        assert timedelta(minutes=14) < time_diff < timedelta(minutes=16)

    def test_create_refresh_token(self):
        """Refresh token should be created with correct type."""
        user_id = uuid4()
        token = create_refresh_token(user_id)

        payload, error = decode_token(token, expected_type=TokenType.REFRESH)
        assert error is None
        assert payload is not None
        assert payload.type == TokenType.REFRESH

    def test_access_and_refresh_tokens_differ(self):
        """Access and refresh tokens should be different."""
        user_id = uuid4()
        access = create_access_token(user_id)
        refresh = create_refresh_token(user_id)

        assert access != refresh


class TestTokenValidation:
    """Tests for JWT token validation."""

    def test_validate_valid_access_token(self):
        """Valid access token should be validated successfully."""
        user_id = uuid4()
        token = create_access_token(user_id)

        payload, error = validate_access_token(token)

        assert error is None
        assert payload is not None
        assert str(payload.user_id) == str(user_id)
        assert payload.type == TokenType.ACCESS

    def test_validate_valid_refresh_token(self):
        """Valid refresh token should be validated successfully."""
        user_id = uuid4()
        token = create_refresh_token(user_id)

        payload, error = validate_refresh_token(token)

        assert error is None
        assert payload is not None
        assert str(payload.user_id) == str(user_id)
        assert payload.type == TokenType.REFRESH

    def test_validate_wrong_token_type(self):
        """Using wrong token type should fail."""
        user_id = uuid4()
        access_token = create_access_token(user_id)

        # Try to validate access token as refresh token
        payload, error = validate_refresh_token(access_token)

        assert payload is None
        assert error is not None
        assert "Invalid token type" in error

    def test_validate_invalid_token(self):
        """Invalid token should fail validation."""
        payload, error = validate_access_token("invalid.token.here")

        assert payload is None
        assert error is not None

    def test_validate_tampered_token(self):
        """Tampered token should fail validation."""
        user_id = uuid4()
        token = create_access_token(user_id)
        # Tamper with the token
        tampered = token[:-5] + "xxxxx"

        payload, error = validate_access_token(tampered)

        assert payload is None
        assert error is not None


class TestAPIKeyGeneration:
    """Tests for API key operations."""

    def test_generate_api_key(self):
        """API key should be generated with prefix."""
        key = generate_api_key(prefix="wf")

        assert key.startswith("wf_")
        assert len(key) > 10

    def test_generate_api_key_custom_prefix(self):
        """API key should use custom prefix."""
        key = generate_api_key(prefix="test")

        assert key.startswith("test_")

    def test_api_key_uniqueness(self):
        """Generated API keys should be unique."""
        keys = [generate_api_key() for _ in range(100)]
        unique_keys = set(keys)

        assert len(unique_keys) == 100

    def test_hash_api_key(self):
        """API key hashing should be deterministic."""
        key = "wf_test_key_123"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)

        assert hash1 == hash2
        assert hash1 != key


class TestUserModel:
    """Tests for User model."""

    def test_user_creation(self):
        """User should be created with default values."""
        user = User(
            email="test@example.com",
            hashed_password="hashed_password_here",
        )

        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.full_name is None

    def test_user_email_normalization(self):
        """User email should be normalized to lowercase via validator."""
        # Note: SQLModel validators run during model_validate, not direct __init__
        user = User.model_validate({
            "email": "TEST@EXAMPLE.COM",
            "hashed_password": "hashed",
        })

        assert user.email == "test@example.com"

    def test_user_display_name_with_full_name(self):
        """Display name should use full name when available."""
        user = User(
            email="test@example.com",
            hashed_password="hashed",
            full_name="John Doe",
        )

        assert user.display_name == "John Doe"

    def test_user_display_name_without_full_name(self):
        """Display name should use email prefix when no full name."""
        user = User(
            email="john.doe@example.com",
            hashed_password="hashed",
        )

        assert user.display_name == "john.doe"

    def test_user_to_dict(self):
        """User to_dict should exclude sensitive data by default."""
        user = User(
            email="test@example.com",
            hashed_password="secret_hash",
            full_name="Test User",
        )

        data = user.to_dict()

        assert "email" in data
        assert "full_name" in data
        assert "hashed_password" not in data

    def test_user_to_dict_with_sensitive(self):
        """User to_dict should include sensitive data when requested."""
        user = User(
            email="test@example.com",
            hashed_password="secret_hash",
        )

        data = user.to_dict(include_sensitive=True)

        assert "hashed_password" in data

    def test_user_is_admin_alias(self):
        """is_admin should be alias for is_superuser."""
        admin = User(
            email="admin@example.com",
            hashed_password="hashed",
            is_superuser=True,
        )
        regular = User(
            email="user@example.com",
            hashed_password="hashed",
            is_superuser=False,
        )

        assert admin.is_admin is True
        assert regular.is_admin is False
