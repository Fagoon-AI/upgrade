"""
User model factory for test data generation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import factory
from faker import Faker

from src.models.sql.workflow.user import User
from src.core.security import get_password_hash

fake = Faker()


class UserFactory(factory.Factory):
    """
    Factory for creating User instances.

    Usage:
        # Create with defaults
        user = UserFactory()

        # Create with specific values
        user = UserFactory(email="specific@email.com")

        # Create superuser
        admin = UserFactory(is_superuser=True)

        # Create inactive user
        inactive = UserFactory(is_active=False)

        # Build without saving (just returns dict-like object)
        user_data = UserFactory.build()
    """

    class Meta:
        model = User

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    email: str = factory.LazyFunction(lambda: fake.unique.email().lower())
    hashed_password: str = factory.LazyFunction(
        lambda: get_password_hash("TestPassword123!")
    )
    full_name: Optional[str] = factory.LazyFunction(fake.name)
    is_active: bool = True
    is_superuser: bool = False
    last_login: Optional[datetime] = None
    created_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    def create_with_password(cls, password: str, **kwargs) -> User:
        """
        Create user with specific password.

        Args:
            password: Plain text password to hash
            **kwargs: Additional user fields

        Returns:
            User instance with hashed password
        """
        return cls(hashed_password=get_password_hash(password), **kwargs)

    @classmethod
    def create_superuser(cls, **kwargs) -> User:
        """Create a superuser."""
        return cls(is_superuser=True, **kwargs)

    @classmethod
    def create_inactive(cls, **kwargs) -> User:
        """Create an inactive user."""
        return cls(is_active=False, **kwargs)

    @classmethod
    def create_batch_users(cls, count: int, **kwargs) -> list[User]:
        """
        Create multiple users.

        Args:
            count: Number of users to create
            **kwargs: Common fields for all users

        Returns:
            List of User instances
        """
        return [cls(**kwargs) for _ in range(count)]


class UserCreateDataFactory(factory.Factory):
    """
    Factory for user registration request data.

    Used for testing auth endpoints.
    """

    class Meta:
        model = dict

    email: str = factory.LazyFunction(lambda: fake.unique.email().lower())
    password: str = "TestPassword123!"
    full_name: str = factory.LazyFunction(fake.name)

    @classmethod
    def with_weak_password(cls, **kwargs) -> dict:
        """Create registration data with weak password."""
        return cls(password="weak", **kwargs)

    @classmethod
    def with_invalid_email(cls, **kwargs) -> dict:
        """Create registration data with invalid email."""
        return cls(email="invalid-email", **kwargs)
