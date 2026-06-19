"""WorkflowAPI model — turns published workflows into callable API endpoints."""

import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import DateTime, String, Boolean, Integer, Index, text


class WorkflowAPI(SQLModel, table=True):
    """Maps a workflow to a public API endpoint with key-based auth."""

    __tablename__ = "workflow_api"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    workflow_id: uuid.UUID = Field(
        foreign_key="workflow.id",
        index=True,
        unique=True,
        description="One API per workflow"
    )

    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        index=True,
        description="Owner"
    )

    # Public slug: /api/v1/workflow-api/{slug}/execute
    slug: str = Field(
        sa_column=Column(String(100), unique=True, nullable=False, index=True),
        description="URL-safe unique slug"
    )

    # API key (hashed for storage, shown once on creation)
    api_key_hash: str = Field(
        sa_column=Column(String(128), nullable=False),
        description="SHA-256 hash of the API key"
    )

    api_key_prefix: str = Field(
        sa_column=Column(String(12), nullable=False),
        description="First 8 chars of key for identification (wfapi_xxxxxxxx)"
    )

    # Controls
    is_active: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    rate_limit_per_minute: int = Field(default=60, sa_column=Column(Integer, default=60))
    timeout_seconds: int = Field(default=120, sa_column=Column(Integer, default=120))

    # Usage tracking
    total_calls: int = Field(default=0, sa_column=Column(Integer, default=0))
    last_called_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    # Audit
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    )

    __table_args__ = (
        Index("ix_workflow_api_slug", "slug"),
        Index("ix_workflow_api_workflow", "workflow_id"),
    )

    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        """Returns (raw_key, key_hash, key_prefix)."""
        import hashlib
        raw = f"wfapi_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        prefix = raw[:14]
        return raw, key_hash, prefix

    @staticmethod
    def hash_key(raw_key: str) -> str:
        import hashlib
        return hashlib.sha256(raw_key.encode()).hexdigest()
