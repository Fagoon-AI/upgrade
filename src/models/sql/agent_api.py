import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.security import generate_api_key, hash_api_key
from .base import Base


class AgentAPI(Base):
    """Maps an Agent to a public chat API endpoint with key-based auth."""

    __tablename__ = "agent_api"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Public slug: /api/v1/agent-api/{slug}/chat
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # API key (hashed for storage, shown once on creation)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)

    # Controls
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)

    # Usage tracking
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    last_called_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    agent = relationship("Agent", back_populates="api_key")

    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        """Returns (raw_key, key_hash, key_prefix)."""
        raw = generate_api_key(prefix="agapi")
        key_hash = hash_api_key(raw)
        prefix = raw[:14]
        return raw, key_hash, prefix

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hash_api_key(raw_key)
