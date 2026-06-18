import uuid
import re
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, String, Boolean, Index
from sqlalchemy.orm import validates
from pydantic import field_validator

if TYPE_CHECKING:
    from src.models.sql.workflow.workflow import Workflow
    from src.models.sql.workflow.connection import Connection
    from src.models.sql.workflow.schedule import WorkflowSchedule


# Email validation regex
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


class User(SQLModel, table=True):
    """
    User model for authentication and ownership.

    Features:
    - UUID primary key
    - Email with uniqueness constraint
    - Password hashing (handled by security module)
    - Active/inactive status
    - Superuser flag
    - Login tracking
    - Audit timestamps

    Indexes:
    - Primary key on id
    - Unique index on email
    - Index on is_active for filtering
    - Index on created_at for sorting
    """

    __tablename__ = "user"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique user identifier"
    )

    # Authentication fields
    email: str = Field(
        sa_column=Column(
            String(255),
            unique=True,
            index=True,
            nullable=False
        ),
        description="User email address (unique)"
    )

    hashed_password: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Argon2 hashed password"
    )

    # Profile fields
    full_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="User's full name"
    )

    # Status flags
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, index=True),
        description="Account active status"
    )

    is_superuser: bool = Field(
        default=False,
        sa_column=Column(Boolean, default=False),
        description="Superuser/admin flag"
    )

    # Activity tracking
    last_login: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last successful login timestamp"
    )

    # Audit timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            default=lambda: datetime.now(timezone.utc)
        ),
        description="Account creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc)
        ),
        description="Last update timestamp"
    )

    # Relationships
    workflows: List["Workflow"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    connections: List["Connection"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    schedules: List["WorkflowSchedule"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    # Table configuration
    __table_args__ = (
        Index("ix_user_email_lower", "email"),
        Index("ix_user_active_created", "is_active", "created_at"),
    )

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalizes and validates email."""
        if not v:
            raise ValueError("Email is required")

        v = v.lower().strip()

        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")

        if len(v) > 255:
            raise ValueError("Email too long (max 255 characters)")

        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitizes full name."""
        if not v:
            return None

        v = v.strip()

        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)

        if len(v) > 255:
            v = v[:255]

        return v if v else None

    # ============================================================
    # METHODS
    # ============================================================

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """
        Converts user to dictionary.

        Args:
            include_sensitive: Include sensitive fields (password hash)

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_sensitive:
            data["hashed_password"] = self.hashed_password

        return data

    def to_public_dict(self) -> dict:
        """
        Converts to public-safe dictionary (no sensitive data).

        Returns:
            Public dictionary representation
        """
        return {
            "id": str(self.id),
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def display_name(self) -> str:
        """Gets display name (full_name or email prefix)."""
        if self.full_name:
            return self.full_name
        return self.email.split("@")[0]

    @property
    def is_admin(self) -> bool:
        """Alias for is_superuser."""
        return self.is_superuser

    def __repr__(self) -> str:
        return f"<User {self.email}>"

    def __str__(self) -> str:
        return self.display_name