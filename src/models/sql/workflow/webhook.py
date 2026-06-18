import uuid
import secrets
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, DateTime, String, Integer, Index, Text, Boolean, text, JSON
from pydantic import field_validator


# ============================================================
# CONFIGURATION
# ============================================================

# Slug length
SLUG_LENGTH = 32

# Secret key length
SECRET_KEY_LENGTH = 64

# Supported providers
SUPPORTED_PROVIDERS = {
    "generic",
    "github",
    "stripe",
    "slack",
    "discord",
    "twilio",
    "sendgrid",
    "shopify",
    "zendesk",
    "custom"
}

# Rate limit defaults
DEFAULT_RATE_LIMIT = 100  # requests per minute


# ============================================================
# ENUMS
# ============================================================

class WebhookStatus(str, Enum):
    """Webhook status."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"


class WebhookEventType(str, Enum):
    """Event types for tracking."""
    RECEIVED = "received"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


# ============================================================
# WEBHOOK MODEL
# ============================================================

class Webhook(SQLModel, table=True):
    """
    Webhook configuration for external triggers.

    Features:
    - UUID primary key
    - Unique slug for URL
    - Secret key for HMAC validation
    - Provider-specific handling
    - Rate limiting
    - Health tracking
    - Event history

    URL Format:
        POST /api/v1/hooks/{slug}

    Security:
    - HMAC signature validation
    - Rate limiting per webhook
    - IP allowlisting (optional)
    - Secret rotation support

    Indexes:
    - Primary key on id
    - Unique index on slug
    - Index on workflow_id
    """

    __tablename__ = "webhook"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique webhook identifier"
    )

    # Association
    workflow_id: uuid.UUID = Field(
        foreign_key="workflow.id",
        index=True,
        description="Associated workflow ID"
    )

    # Identification
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Human-readable webhook name"
    )

    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Webhook description"
    )

    # URL slug (unique identifier in URL)
    slug: str = Field(
        sa_column=Column(String(64), unique=True, index=True, nullable=False),
        default_factory=lambda: secrets.token_urlsafe(SLUG_LENGTH)[:SLUG_LENGTH],
        description="URL slug for webhook endpoint"
    )

    # Security
    secret_key: Optional[str] = Field(
        default=None,
        sa_column=Column(String(128)),
        description="HMAC secret for signature validation"
    )

    secret_key_rotated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last secret rotation timestamp"
    )

    # Provider configuration
    provider: str = Field(
        default="generic",
        sa_column=Column(String(50)),
        description="Webhook provider type"
    )

    # Status
    status: str = Field(
        default=WebhookStatus.ACTIVE.value,
        sa_column=Column(String(20)),
        description="Webhook status"
    )

    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True),
        description="Legacy active flag"
    )

    # Rate limiting
    rate_limit: int = Field(
        default=DEFAULT_RATE_LIMIT,
        description="Max requests per minute"
    )

    rate_limit_window: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Current rate limit window start"
    )

    rate_limit_count: int = Field(
        default=0,
        description="Requests in current window"
    )

    # IP allowlist (JSON array)
    allowed_ips: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="JSON array of allowed IPs"
    )

    # Health tracking
    last_triggered_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last successful trigger"
    )

    total_triggers: int = Field(
        default=0,
        description="Total trigger count"
    )

    failed_triggers: int = Field(
        default=0,
        description="Failed trigger count"
    )

    consecutive_failures: int = Field(
        default=0,
        description="Consecutive failures (for health)"
    )

    # Configuration
    config_json: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Additional configuration JSON"
    )

    # Timestamps
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
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Last update timestamp"
    )

    # Table configuration
    __table_args__ = (
        # Index for workflow queries
        Index("ix_webhook_workflow_active", "workflow_id", "is_active"),

        # Index for status queries
        Index("ix_webhook_status", "status"),
    )

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("provider", mode="before")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validates provider type."""
        if not v:
            return "generic"

        v = v.lower().strip()

        if v not in SUPPORTED_PROVIDERS:
            return "custom"

        return v

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validates name."""
        if not v:
            raise ValueError("Webhook name is required")

        v = v.strip()

        if len(v) > 255:
            v = v[:255]

        return v

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validates status."""
        if not v:
            return WebhookStatus.ACTIVE.value

        v = v.lower().strip()

        valid_statuses = {s.value for s in WebhookStatus}
        if v not in valid_statuses:
            return WebhookStatus.ACTIVE.value

        return v

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_enabled(self) -> bool:
        """Checks if webhook is enabled."""
        return self.is_active and self.status == WebhookStatus.ACTIVE.value

    @property
    def endpoint_url(self) -> str:
        """Gets webhook endpoint URL (relative)."""
        return f"/api/v1/hooks/{self.slug}"

    @property
    def success_rate(self) -> float:
        """Calculates success rate."""
        if self.total_triggers == 0:
            return 100.0

        successful = self.total_triggers - self.failed_triggers
        return round((successful / self.total_triggers) * 100, 2)

    @property
    def is_healthy(self) -> bool:
        """Checks webhook health."""
        # Unhealthy if 5+ consecutive failures
        if self.consecutive_failures >= 5:
            return False

        # Unhealthy if success rate below 50%
        if self.total_triggers > 10 and self.success_rate < 50:
            return False

        return True

    # ============================================================
    # SECRET MANAGEMENT
    # ============================================================

    def generate_secret(self) -> str:
        """Generates a new secret key."""
        self.secret_key = secrets.token_urlsafe(SECRET_KEY_LENGTH)
        self.secret_key_rotated_at = datetime.now(timezone.utc)
        return self.secret_key

    def rotate_secret(self) -> str:
        """Rotates the secret key."""
        return self.generate_secret()

    def verify_signature(
            self,
            payload: bytes,
            signature: str
    ) -> bool:
        """
        Verifies HMAC signature.

        Args:
            payload: Request body bytes
            signature: Signature from header

        Returns:
            True if signature is valid
        """
        if not self.secret_key:
            return True  # No secret = no verification

        if not signature:
            return False

        try:
            # Provider-specific signature handling
            if self.provider == "github":
                return self._verify_github_signature(payload, signature)
            elif self.provider == "stripe":
                return self._verify_stripe_signature(payload, signature)
            else:
                return self._verify_generic_signature(payload, signature)
        except Exception:
            return False

    def _verify_generic_signature(
            self,
            payload: bytes,
            signature: str
    ) -> bool:
        """Verifies generic HMAC-SHA256 signature."""
        expected = hmac.new(
            self.secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _verify_github_signature(
            self,
            payload: bytes,
            signature: str
    ) -> bool:
        """Verifies GitHub webhook signature."""
        expected = "sha256=" + hmac.new(
            self.secret_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _verify_stripe_signature(
            self,
            payload: bytes,
            signature: str
    ) -> bool:
        """Verifies Stripe webhook signature."""
        try:
            parts = dict(x.split("=") for x in signature.split(","))
            timestamp = parts.get("t")
            v1_sig = parts.get("v1")

            if not timestamp or not v1_sig:
                return False

            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(
                self.secret_key.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, v1_sig)
        except Exception:
            return False

    # ============================================================
    # RATE LIMITING
    # ============================================================

    def check_rate_limit(self) -> bool:
        """
        Checks and updates rate limit.

        Returns:
            True if request is allowed
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)

        # Reset window if expired
        if not self.rate_limit_window or self.rate_limit_window < window_start:
            self.rate_limit_window = now
            self.rate_limit_count = 1
            return True

        # Check limit
        if self.rate_limit_count >= self.rate_limit:
            self.status = WebhookStatus.RATE_LIMITED.value
            return False

        self.rate_limit_count += 1
        return True

    # ============================================================
    # IP ALLOWLIST
    # ============================================================

    def get_allowed_ips(self) -> List[str]:
        """Gets list of allowed IPs."""
        if not self.allowed_ips:
            return []

        try:
            import json
            return json.loads(self.allowed_ips)
        except Exception:
            return []

    def set_allowed_ips(self, ips: List[str]) -> None:
        """Sets allowed IP list."""
        import json
        self.allowed_ips = json.dumps(ips)

    def is_ip_allowed(self, ip: str) -> bool:
        """Checks if IP is allowed."""
        allowed = self.get_allowed_ips()

        # If no allowlist, all IPs are allowed
        if not allowed:
            return True

        return ip in allowed

    # ============================================================
    # HEALTH TRACKING
    # ============================================================

    def record_success(self) -> None:
        """Records successful trigger."""
        self.last_triggered_at = datetime.now(timezone.utc)
        self.total_triggers += 1
        self.consecutive_failures = 0

        # Reset rate limit status if applicable
        if self.status == WebhookStatus.RATE_LIMITED.value:
            self.status = WebhookStatus.ACTIVE.value

    def record_failure(self) -> None:
        """Records failed trigger."""
        self.total_triggers += 1
        self.failed_triggers += 1
        self.consecutive_failures += 1

        # Auto-disable after too many failures
        if self.consecutive_failures >= 10:
            self.status = WebhookStatus.DISABLED.value

    # ============================================================
    # SERIALIZATION
    # ============================================================

    def get_config(self) -> Dict[str, Any]:
        """Gets additional configuration."""
        if not self.config_json:
            return {}

        try:
            import json
            return json.loads(self.config_json)
        except Exception:
            return {}

    def set_config(self, config: Dict[str, Any]) -> None:
        """Sets additional configuration."""
        import json
        self.config_json = json.dumps(config)

    def to_dict(self, include_secret: bool = False) -> Dict[str, Any]:
        """
        Converts to dictionary.

        Args:
            include_secret: Include secret key (for admin only)

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "name": self.name,
            "description": self.description,
            "slug": self.slug,
            "endpoint_url": self.endpoint_url,
            "provider": self.provider,
            "status": self.status,
            "is_active": self.is_active,
            "is_enabled": self.is_enabled,
            "is_healthy": self.is_healthy,
            "rate_limit": self.rate_limit,
            "has_secret": bool(self.secret_key),
            "total_triggers": self.total_triggers,
            "success_rate": self.success_rate,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_secret and self.secret_key:
            data["secret_key"] = self.secret_key
            data["secret_key_rotated_at"] = (
                self.secret_key_rotated_at.isoformat()
                if self.secret_key_rotated_at else None
            )

        return data

    def __repr__(self) -> str:
        return f"<Webhook {self.name} [{self.slug}]>"