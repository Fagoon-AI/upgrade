from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index


# ============================================================
# USAGE RECORD MODEL
# ============================================================

class UsageRecord(SQLModel, table=True):
    """
    Records individual API usage events.

    One record per AI node execution that consumes tokens.

    Table: usage_records
    """
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("idx_usage_user_created", "user_id", "created_at"),
        Index("idx_usage_execution", "execution_id"),
        Index("idx_usage_workflow", "workflow_id"),
        Index("idx_usage_provider_model", "provider", "model"),
    )

    # Primary key
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Foreign keys (not enforced, for flexibility)
    user_id: UUID = Field(index=True)
    workflow_id: UUID = Field(index=True)
    execution_id: UUID = Field(index=True)

    # Node identification
    node_id: str = Field(max_length=100)
    node_type: str = Field(max_length=50)

    # Provider information
    provider: str = Field(max_length=50)  # gemini, openai, anthropic, perplexity, mistral
    model: str = Field(max_length=100)     # specific model name

    # Token counts
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

    # Cost (stored as string for precision)
    cost_usd: str = Field(default="0", max_length=20)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Optional metadata
    latency_ms: Optional[int] = Field(default=None)
    request_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


# ============================================================
# USER QUOTA MODEL
# ============================================================

class UserQuota(SQLModel, table=True):
    """
    User quota configuration and current usage tracking.

    One record per user. Resets monthly.

    Table: user_quotas
    """
    __tablename__ = "user_quotas"

    # Primary key
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # User reference (unique constraint)
    user_id: UUID = Field(unique=True, index=True)

    # Plan information
    plan: str = Field(default="free", max_length=20)  # free, pro, enterprise

    # Monthly limits
    monthly_token_limit: int = Field(default=100_000)
    monthly_execution_limit: int = Field(default=100)
    monthly_cost_limit_usd: str = Field(default="10.00", max_length=20)

    # Current billing period start
    period_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    )

    # Current period usage
    current_tokens: int = Field(default=0)
    current_executions: int = Field(default=0)
    current_cost_usd: str = Field(default="0", max_length=20)

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# MONTHLY USAGE SUMMARY MODEL
# ============================================================

class MonthlyUsageSummary(SQLModel, table=True):
    """
    Aggregated monthly usage for reporting and analytics.

    Pre-computed summaries for fast dashboard queries.

    Table: monthly_usage_summaries
    """
    __tablename__ = "monthly_usage_summaries"
    __table_args__ = (
        Index("idx_monthly_user_period", "user_id", "period_year", "period_month"),
    )

    # Primary key
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # User reference
    user_id: UUID = Field(index=True)

    # Period identification
    period_year: int
    period_month: int  # 1-12

    # Aggregate metrics
    total_executions: int = Field(default=0)
    total_tokens: int = Field(default=0)
    total_input_tokens: int = Field(default=0)
    total_output_tokens: int = Field(default=0)
    total_cost_usd: str = Field(default="0", max_length=20)

    # Breakdown by provider (JSON)
    usage_by_provider: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Top workflows by usage (JSON array)
    top_workflows: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# PLAN CONFIGURATIONS
# ============================================================

PLAN_LIMITS = {
    "free": {
        "monthly_token_limit": 100_000,
        "monthly_execution_limit": 100,
        "monthly_cost_limit_usd": "10.00",
    },
    "pro": {
        "monthly_token_limit": 1_000_000,
        "monthly_execution_limit": 1_000,
        "monthly_cost_limit_usd": "100.00",
    },
    "enterprise": {
        "monthly_token_limit": 10_000_000,
        "monthly_execution_limit": 10_000,
        "monthly_cost_limit_usd": "1000.00",
    },
}


def get_plan_limits(plan: str) -> Dict[str, Any]:
    """Returns limits for a given plan."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])