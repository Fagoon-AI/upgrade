"""
Cost Tracking Service.
Service layer for API usage tracking, cost calculation, and quota enforcement.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from loguru import logger

from src.models.sql.workflow.usage import UsageRecord, UserQuota, MonthlyUsageSummary, get_plan_limits


# RATE CARDS (Cost per 1K tokens in USD)

RATE_CARDS: Dict[str, Dict[str, Dict[str, float]]] = {
    "gemini": {
        "gemini-2.5-pro": {"input": 0.00125, "output": 0.00500},
        "gemini-2.5-flash": {"input": 0.000075, "output": 0.0003},
        "gemini-2.0-flash": {"input": 0.00010, "output": 0.0004},
        "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
        "gemini-1.5-pro": {"input": 0.00125, "output": 0.00500},
        "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    },
    "openai": {
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "o1": {"input": 0.015, "output": 0.06},
        "o1-mini": {"input": 0.003, "output": 0.012},
    },
    "anthropic": {
        "claude-sonnet-4": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-5-haiku": {"input": 0.0008, "output": 0.004},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    },
    "perplexity": {
        "sonar": {"input": 0.001, "output": 0.001},
        "sonar-pro": {"input": 0.003, "output": 0.015},
    },
    "mistral": {
        "mistral-large": {"input": 0.002, "output": 0.006},
        "mistral-small": {"input": 0.0001, "output": 0.0003},
        "pixtral": {"input": 0.0001, "output": 0.0003},
    }
}

DEFAULT_RATES = {"input": 0.001, "output": 0.002}


# COST CALCULATOR

class CostCalculator:
    """Static methods for cost calculation."""

    @staticmethod
    def calculate(
            provider: str,
            model: str,
            input_tokens: int,
            output_tokens: int
    ) -> Decimal:
        """
        Calculates cost for token usage.

        Args:
            provider: AI provider (gemini, openai, etc.)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD as Decimal (6 decimal places)
        """
        provider_rates = RATE_CARDS.get(provider.lower(), {})
        model_rates = provider_rates.get(model, DEFAULT_RATES)

        input_cost = Decimal(str(input_tokens)) / Decimal("1000") * Decimal(str(model_rates["input"]))
        output_cost = Decimal(str(output_tokens)) / Decimal("1000") * Decimal(str(model_rates["output"]))

        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    @staticmethod
    def get_rate(provider: str, model: str) -> Dict[str, float]:
        """Gets rate for a provider/model combination."""
        provider_rates = RATE_CARDS.get(provider.lower(), {})
        return provider_rates.get(model, DEFAULT_RATES)

    @staticmethod
    def estimate_monthly_cost(
            daily_executions: int,
            avg_tokens_per_execution: int,
            provider: str = "gemini",
            model: str = "gemini-2.5-flash"
    ) -> Decimal:
        """Estimates monthly cost based on usage patterns."""
        daily_tokens = daily_executions * avg_tokens_per_execution
        monthly_tokens = daily_tokens * 30

        # Assume 30% input, 70% output ratio (typical for chat)
        input_tokens = int(monthly_tokens * 0.3)
        output_tokens = int(monthly_tokens * 0.7)

        return CostCalculator.calculate(provider, model, input_tokens, output_tokens)


# QUOTA EXCEEDED EXCEPTION

class QuotaExceededError(Exception):
    """Raised when user exceeds their quota."""

    def __init__(
            self,
            message: str,
            quota_type: str,
            limit: Any,
            current: Any
    ):
        super().__init__(message)
        self.quota_type = quota_type
        self.limit = limit
        self.current = current

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": "QUOTA_EXCEEDED",
            "message": str(self),
            "quota_type": self.quota_type,
            "limit": self.limit,
            "current": self.current
        }


# USAGE TRACKING SERVICE

class UsageTrackingService:
    """
    Service for tracking and managing API usage.

    Features:
    - Record usage per node execution
    - Update user quotas
    - Check quota limits
    - Generate usage reports
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_usage(
            self,
            user_id: UUID,
            workflow_id: UUID,
            execution_id: UUID,
            node_id: str,
            node_type: str,
            provider: str,
            model: str,
            input_tokens: int,
            output_tokens: int,
            latency_ms: Optional[int] = None,
            metadata: Optional[Dict[str, Any]] = None
    ) -> UsageRecord:
        """
        Records a usage event and updates user quota.

        Args:
            user_id: User UUID
            workflow_id: Workflow UUID
            execution_id: Execution UUID
            node_id: Node ID within workflow
            node_type: Type of node (geminiNode, etc.)
            provider: AI provider name
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            latency_ms: Optional API latency
            metadata: Optional additional metadata

        Returns:
            Created UsageRecord
        """
        # Calculate cost
        cost = CostCalculator.calculate(provider, model, input_tokens, output_tokens)

        # Create record
        record = UsageRecord(
            user_id=user_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=str(cost),
            latency_ms=latency_ms,
            request_metadata=metadata
        )

        self.db.add(record)

        # Update user quota
        await self._update_user_quota(
            user_id=user_id,
            tokens=input_tokens + output_tokens,
            cost=cost
        )

        await self.db.commit()
        await self.db.refresh(record)

        logger.debug(
            f"Usage recorded: {node_type} - {input_tokens + output_tokens} tokens, ${cost}",
            extra={
                "user_id": str(user_id),
                "execution_id": str(execution_id),
                "provider": provider,
                "model": model
            }
        )

        return record

    async def _update_user_quota(
            self,
            user_id: UUID,
            tokens: int,
            cost: Decimal
    ) -> UserQuota:
        """Updates user's current period usage."""
        # Get or create quota
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalars().first()

        if not quota:
            # Create default quota
            plan_limits = get_plan_limits("free")
            quota = UserQuota(
                user_id=user_id,
                **plan_limits
            )
            self.db.add(quota)
            await self.db.flush()

        # Check if period needs reset (new month)
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if quota.period_start < period_start:
            logger.info(f"Resetting quota for user {user_id} - new billing period")
            quota.period_start = period_start
            quota.current_tokens = 0
            quota.current_executions = 0
            quota.current_cost_usd = "0"

        # Update counters
        quota.current_tokens += tokens
        quota.current_cost_usd = str(
            Decimal(quota.current_cost_usd) + cost
        )
        quota.updated_at = now

        return quota

    async def increment_executions(self, user_id: UUID) -> None:
        """Increments execution count for a user."""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalars().first()

        if quota:
            quota.current_executions += 1
            quota.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

    async def check_quota(self, user_id: UUID) -> Dict[str, Any]:
        """
        Checks if user is within quota limits.

        Returns:
            Dict with quota status and remaining limits
        """
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalars().first()

        if not quota:
            # No quota record - use defaults
            plan_limits = get_plan_limits("free")
            return {
                "within_limits": True,
                "plan": "free",
                "tokens_remaining": plan_limits["monthly_token_limit"],
                "executions_remaining": plan_limits["monthly_execution_limit"],
                "cost_remaining_usd": plan_limits["monthly_cost_limit_usd"],
                "current_period": {
                    "tokens_used": 0,
                    "executions_used": 0,
                    "cost_usd": "0"
                },
                "limits": plan_limits
            }

        # Calculate remaining
        tokens_remaining = quota.monthly_token_limit - quota.current_tokens
        executions_remaining = quota.monthly_execution_limit - quota.current_executions
        cost_remaining = Decimal(quota.monthly_cost_limit_usd) - Decimal(quota.current_cost_usd)

        within_limits = (
                tokens_remaining > 0 and
                executions_remaining > 0 and
                cost_remaining > 0
        )

        return {
            "within_limits": within_limits,
            "plan": quota.plan,
            "tokens_remaining": max(0, tokens_remaining),
            "executions_remaining": max(0, executions_remaining),
            "cost_remaining_usd": str(max(Decimal("0"), cost_remaining)),
            "current_period": {
                "start": quota.period_start.isoformat(),
                "tokens_used": quota.current_tokens,
                "executions_used": quota.current_executions,
                "cost_usd": quota.current_cost_usd
            },
            "limits": {
                "tokens": quota.monthly_token_limit,
                "executions": quota.monthly_execution_limit,
                "cost_usd": quota.monthly_cost_limit_usd
            }
        }

    async def get_execution_usage(self, execution_id: UUID) -> Dict[str, Any]:
        """Gets usage summary for an execution."""
        result = await self.db.execute(
            select(UsageRecord).where(UsageRecord.execution_id == execution_id)
        )
        records = result.scalars().all()

        if not records:
            return {
                "execution_id": str(execution_id),
                "total_tokens": 0,
                "total_cost_usd": "0",
                "nodes": []
            }

        total_cost = sum(Decimal(r.cost_usd) for r in records)

        return {
            "execution_id": str(execution_id),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_input_tokens": sum(r.input_tokens for r in records),
            "total_output_tokens": sum(r.output_tokens for r in records),
            "total_cost_usd": str(total_cost),
            "nodes": [
                {
                    "node_id": r.node_id,
                    "node_type": r.node_type,
                    "provider": r.provider,
                    "model": r.model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "total_tokens": r.total_tokens,
                    "cost_usd": r.cost_usd,
                    "latency_ms": r.latency_ms
                }
                for r in records
            ]
        }

    async def get_workflow_usage(
            self,
            workflow_id: UUID,
            days: int = 30
    ) -> Dict[str, Any]:
        """Gets usage summary for a workflow over a period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.workflow_id == workflow_id,
                    UsageRecord.created_at >= cutoff
                )
            )
            .order_by(UsageRecord.created_at.desc())
        )
        records = result.scalars().all()

        if not records:
            return {
                "workflow_id": str(workflow_id),
                "period_days": days,
                "total_executions": 0,
                "total_tokens": 0,
                "total_cost_usd": "0",
                "by_provider": {}
            }

        executions = set(r.execution_id for r in records)
        total_cost = sum(Decimal(r.cost_usd) for r in records)

        return {
            "workflow_id": str(workflow_id),
            "period_days": days,
            "total_executions": len(executions),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_input_tokens": sum(r.input_tokens for r in records),
            "total_output_tokens": sum(r.output_tokens for r in records),
            "total_cost_usd": str(total_cost),
            "avg_tokens_per_execution": sum(r.total_tokens for r in records) // max(1, len(executions)),
            "by_provider": self._aggregate_by_provider(records)
        }

    async def get_user_usage(
            self,
            user_id: UUID,
            days: int = 30
    ) -> Dict[str, Any]:
        """Gets usage summary for a user over a period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.user_id == user_id,
                    UsageRecord.created_at >= cutoff
                )
            )
            .order_by(UsageRecord.created_at.desc())
        )
        records = result.scalars().all()

        # Get quota info
        quota_status = await self.check_quota(user_id)

        if not records:
            return {
                "user_id": str(user_id),
                "period_days": days,
                "total_executions": 0,
                "total_workflows": 0,
                "total_tokens": 0,
                "total_cost_usd": "0",
                "by_provider": {},
                "by_workflow": [],
                "daily_trend": [],
                "quota": quota_status
            }

        executions = set(r.execution_id for r in records)
        workflows = set(r.workflow_id for r in records)
        total_cost = sum(Decimal(r.cost_usd) for r in records)

        return {
            "user_id": str(user_id),
            "period_days": days,
            "total_executions": len(executions),
            "total_workflows": len(workflows),
            "total_tokens": sum(r.total_tokens for r in records),
            "total_cost_usd": str(total_cost),
            "by_provider": self._aggregate_by_provider(records),
            "by_workflow": self._aggregate_by_workflow(records),
            "daily_trend": self._calculate_daily_trend(records),
            "quota": quota_status
        }

    def _aggregate_by_provider(self, records: List[UsageRecord]) -> Dict[str, Any]:
        """Aggregates usage by provider."""
        by_provider: Dict[str, Dict[str, Any]] = {}

        for r in records:
            if r.provider not in by_provider:
                by_provider[r.provider] = {
                    "tokens": 0,
                    "cost_usd": Decimal("0"),
                    "models": {}
                }

            by_provider[r.provider]["tokens"] += r.total_tokens
            by_provider[r.provider]["cost_usd"] += Decimal(r.cost_usd)

            if r.model not in by_provider[r.provider]["models"]:
                by_provider[r.provider]["models"][r.model] = {
                    "tokens": 0,
                    "cost_usd": Decimal("0"),
                    "calls": 0
                }

            by_provider[r.provider]["models"][r.model]["tokens"] += r.total_tokens
            by_provider[r.provider]["models"][r.model]["cost_usd"] += Decimal(r.cost_usd)
            by_provider[r.provider]["models"][r.model]["calls"] += 1

        # Convert Decimals to strings for JSON serialization
        for provider in by_provider:
            by_provider[provider]["cost_usd"] = str(by_provider[provider]["cost_usd"])
            for model in by_provider[provider]["models"]:
                by_provider[provider]["models"][model]["cost_usd"] = str(
                    by_provider[provider]["models"][model]["cost_usd"]
                )

        return by_provider

    def _aggregate_by_workflow(self, records: List[UsageRecord]) -> List[Dict[str, Any]]:
        """Aggregates usage by workflow, returns top 10."""
        by_workflow: Dict[UUID, Dict[str, Any]] = {}

        for r in records:
            if r.workflow_id not in by_workflow:
                by_workflow[r.workflow_id] = {
                    "workflow_id": str(r.workflow_id),
                    "executions": set(),
                    "tokens": 0,
                    "cost_usd": Decimal("0")
                }

            by_workflow[r.workflow_id]["executions"].add(r.execution_id)
            by_workflow[r.workflow_id]["tokens"] += r.total_tokens
            by_workflow[r.workflow_id]["cost_usd"] += Decimal(r.cost_usd)

        result = []
        for wf in by_workflow.values():
            result.append({
                "workflow_id": wf["workflow_id"],
                "execution_count": len(wf["executions"]),
                "tokens": wf["tokens"],
                "cost_usd": str(wf["cost_usd"])
            })

        # Sort by cost descending
        result.sort(key=lambda x: Decimal(x["cost_usd"]), reverse=True)
        return result[:10]

    def _calculate_daily_trend(self, records: List[UsageRecord]) -> List[Dict[str, Any]]:
        """Calculates daily usage trend."""
        daily: Dict[str, Dict[str, Any]] = {}

        for r in records:
            date_key = r.created_at.strftime("%Y-%m-%d")

            if date_key not in daily:
                daily[date_key] = {
                    "date": date_key,
                    "tokens": 0,
                    "cost_usd": Decimal("0"),
                    "executions": set()
                }

            daily[date_key]["tokens"] += r.total_tokens
            daily[date_key]["cost_usd"] += Decimal(r.cost_usd)
            daily[date_key]["executions"].add(r.execution_id)

        result = []
        for d in sorted(daily.values(), key=lambda x: x["date"]):
            result.append({
                "date": d["date"],
                "tokens": d["tokens"],
                "cost_usd": str(d["cost_usd"]),
                "executions": len(d["executions"])
            })

        return result


# QUOTA ENFORCEMENT FUNCTION

async def check_and_enforce_quota(
        db: AsyncSession,
        user_id: UUID
) -> Dict[str, Any]:
    """
    Checks quota and raises exception if exceeded.

    Should be called before workflow execution starts.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Quota status dict if within limits

    Raises:
        QuotaExceededError: If any limit is exceeded
    """
    service = UsageTrackingService(db)
    quota_status = await service.check_quota(user_id)

    if not quota_status["within_limits"]:
        if quota_status["executions_remaining"] <= 0:
            raise QuotaExceededError(
                "Monthly execution limit reached. Please upgrade your plan.",
                quota_type="executions",
                limit=quota_status["limits"]["executions"],
                current=quota_status["current_period"]["executions_used"]
            )

        if quota_status["tokens_remaining"] <= 0:
            raise QuotaExceededError(
                "Monthly token limit reached. Please upgrade your plan.",
                quota_type="tokens",
                limit=quota_status["limits"]["tokens"],
                current=quota_status["current_period"]["tokens_used"]
            )

        if Decimal(quota_status["cost_remaining_usd"]) <= 0:
            raise QuotaExceededError(
                "Monthly cost limit reached. Please upgrade your plan.",
                quota_type="cost",
                limit=quota_status["limits"]["cost_usd"],
                current=quota_status["current_period"]["cost_usd"]
            )

    return quota_status


# HELPER FUNCTION FOR NODE INTEGRATION

async def track_node_usage(
        db: AsyncSession,
        context: Any,  # ExecutionContext
        node_type: str,
        node_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: Optional[int] = None
) -> UsageRecord:
    """
    Helper function for AI nodes to track their usage.

    Usage in node execute() method:

        from src.services.workflow.cost_tracking import track_node_usage

        async def execute(self, db, context, input_data):
            # ... make API call ...

            # Track usage
            await track_node_usage(
                db=db,
                context=context,
                node_type=self.node_type,
                node_id=node_id,
                provider="gemini",
                model="gemini-2.5-flash",
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
                latency_ms=latency
            )

            return {"output_text": response.text}
    """
    service = UsageTrackingService(db)

    return await service.record_usage(
        user_id=context.user_id,
        workflow_id=UUID(context.workflow_id),
        execution_id=UUID(context.execution_id),
        node_id=node_id,
        node_type=node_type,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms
    )


# UPDATE USER PLAN FUNCTION

async def update_user_plan(
        db: AsyncSession,
        user_id: UUID,
        new_plan: str
) -> UserQuota:
    """
    Updates a user's plan and adjusts their limits.

    Args:
        db: Database session
        user_id: User UUID
        new_plan: New plan name (free, pro, enterprise)

    Returns:
        Updated UserQuota
    """
    plan_limits = get_plan_limits(new_plan)

    result = await db.execute(
        select(UserQuota).where(UserQuota.user_id == user_id)
    )
    quota = result.scalars().first()

    if not quota:
        quota = UserQuota(user_id=user_id, plan=new_plan, **plan_limits)
        db.add(quota)
    else:
        quota.plan = new_plan
        quota.monthly_token_limit = plan_limits["monthly_token_limit"]
        quota.monthly_execution_limit = plan_limits["monthly_execution_limit"]
        quota.monthly_cost_limit_usd = plan_limits["monthly_cost_limit_usd"]
        quota.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(quota)

    logger.info(f"Updated user {user_id} to plan: {new_plan}")

    return quota