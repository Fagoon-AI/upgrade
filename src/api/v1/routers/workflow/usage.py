from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow
from src.dao.workflow_dao import WorkflowDAO
from src.schemas.workflow.response import APIResponse
from src.services.workflow.cost_tracking import (
    UsageTrackingService,
    check_and_enforce_quota,
    QuotaExceededError,
    update_user_plan,
    CostCalculator,
    RATE_CARDS
)


router = APIRouter()


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class TokenUsage(BaseModel):
    """Token usage breakdown."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CostBreakdown(BaseModel):
    """Cost breakdown by category."""
    total_cost_usd: str = "0"
    by_provider: Dict[str, Any] = Field(default_factory=dict)


class QuotaStatus(BaseModel):
    """Current quota status."""
    plan: str = "free"
    within_limits: bool = True
    tokens_remaining: int = 0
    executions_remaining: int = 0
    cost_remaining_usd: str = "0"
    current_period: Dict[str, Any] = Field(default_factory=dict)
    limits: Dict[str, Any] = Field(default_factory=dict)


class UsageSummary(BaseModel):
    """Usage summary for a period."""
    period_days: int
    total_executions: int = 0
    total_workflows: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: str = "0"
    by_provider: Dict[str, Any] = Field(default_factory=dict)
    by_workflow: List[Dict[str, Any]] = Field(default_factory=list)
    daily_trend: List[Dict[str, Any]] = Field(default_factory=list)
    quota: Optional[QuotaStatus] = None


class ExecutionUsage(BaseModel):
    """Usage for a single execution."""
    execution_id: str
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: str = "0"
    nodes: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowUsage(BaseModel):
    """Usage for a workflow over a period."""
    workflow_id: str
    workflow_name: Optional[str] = None
    period_days: int
    total_executions: int = 0
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: str = "0"
    avg_tokens_per_execution: int = 0
    by_provider: Dict[str, Any] = Field(default_factory=dict)


class RateCard(BaseModel):
    """Pricing information for a model."""
    provider: str
    model: str
    input_cost_per_1k: float
    output_cost_per_1k: float


class PlanInfo(BaseModel):
    """Plan information."""
    name: str
    monthly_token_limit: int
    monthly_execution_limit: int
    monthly_cost_limit_usd: str


# ============================================================
# USER USAGE ENDPOINTS
# ============================================================

@router.get(
    "/me",
    response_model=APIResponse[UsageSummary],
    summary="Get my usage",
    description="Returns usage summary for the current user"
)
async def get_my_usage(
        days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns usage summary for the authenticated user.

    Includes:
    - Total tokens and cost
    - Breakdown by provider and model
    - Top workflows by usage
    - Daily trend
    - Current quota status
    """
    service = UsageTrackingService(db)

    try:
        usage_data = await service.get_user_usage(current_user.id, days=days)

        # Build quota status
        quota_data = usage_data.get("quota", {})
        quota_status = QuotaStatus(
            plan=quota_data.get("plan", "free"),
            within_limits=quota_data.get("within_limits", True),
            tokens_remaining=quota_data.get("tokens_remaining", 0),
            executions_remaining=quota_data.get("executions_remaining", 0),
            cost_remaining_usd=quota_data.get("cost_remaining_usd", "0"),
            current_period=quota_data.get("current_period", {}),
            limits=quota_data.get("limits", {})
        )

        summary = UsageSummary(
            period_days=days,
            total_executions=usage_data.get("total_executions", 0),
            total_workflows=usage_data.get("total_workflows", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            total_input_tokens=usage_data.get("total_input_tokens", 0),
            total_output_tokens=usage_data.get("total_output_tokens", 0),
            total_cost_usd=usage_data.get("total_cost_usd", "0"),
            by_provider=usage_data.get("by_provider", {}),
            by_workflow=usage_data.get("by_workflow", []),
            daily_trend=usage_data.get("daily_trend", []),
            quota=quota_status
        )

        return APIResponse(
            success=True,
            message=f"Usage summary for last {days} days",
            data=summary
        )

    except Exception as e:
        logger.error(f"Failed to get user usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage data"
        )


@router.get(
    "/quota",
    response_model=APIResponse[QuotaStatus],
    summary="Get quota status",
    description="Returns current quota status and limits"
)
async def get_quota_status(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns current quota status for the authenticated user.

    Use this to check remaining limits before running workflows.
    """
    service = UsageTrackingService(db)

    try:
        quota_data = await service.check_quota(current_user.id)

        quota_status = QuotaStatus(
            plan=quota_data.get("plan", "free"),
            within_limits=quota_data.get("within_limits", True),
            tokens_remaining=quota_data.get("tokens_remaining", 0),
            executions_remaining=quota_data.get("executions_remaining", 0),
            cost_remaining_usd=quota_data.get("cost_remaining_usd", "0"),
            current_period=quota_data.get("current_period", {}),
            limits=quota_data.get("limits", {})
        )

        return APIResponse(
            success=True,
            message="Current quota status",
            data=quota_status
        )

    except Exception as e:
        logger.error(f"Failed to get quota status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quota status"
        )


# ============================================================
# EXECUTION USAGE ENDPOINTS
# ============================================================

@router.get(
    "/executions/{execution_id}",
    response_model=APIResponse[ExecutionUsage],
    summary="Get execution usage",
    description="Returns usage breakdown for a specific execution"
)
async def get_execution_usage(
        execution_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns detailed usage for a specific workflow execution.

    Shows:
    - Total tokens and cost
    - Per-node breakdown
    - Provider and model used for each node
    """
    service = UsageTrackingService(db)

    try:
        usage_data = await service.get_execution_usage(execution_id)

        # Verify user owns this execution (via workflow)
        # Note: In production, add proper authorization check

        execution_usage = ExecutionUsage(
            execution_id=str(execution_id),
            total_tokens=usage_data.get("total_tokens", 0),
            total_input_tokens=usage_data.get("total_input_tokens", 0),
            total_output_tokens=usage_data.get("total_output_tokens", 0),
            total_cost_usd=usage_data.get("total_cost_usd", "0"),
            nodes=usage_data.get("nodes", [])
        )

        return APIResponse(
            success=True,
            message="Execution usage retrieved",
            data=execution_usage
        )

    except Exception as e:
        logger.error(f"Failed to get execution usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve execution usage"
        )


# ============================================================
# WORKFLOW USAGE ENDPOINTS
# ============================================================

@router.get(
    "/workflows/{workflow_id}",
    response_model=APIResponse[WorkflowUsage],
    summary="Get workflow usage",
    description="Returns usage summary for a specific workflow"
)
async def get_workflow_usage(
        workflow_id: UUID,
        days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns usage summary for a specific workflow over a period.

    Shows:
    - Total executions, tokens, and cost
    - Average tokens per execution
    - Breakdown by provider
    """
    # Verify user owns this workflow
    dao = WorkflowDAO(db)
    workflow = await dao.get_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this workflow's usage"
        )

    service = UsageTrackingService(db)

    try:
        usage_data = await service.get_workflow_usage(workflow_id, days=days)

        workflow_usage = WorkflowUsage(
            workflow_id=str(workflow_id),
            workflow_name=workflow.name,
            period_days=days,
            total_executions=usage_data.get("total_executions", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            total_input_tokens=usage_data.get("total_input_tokens", 0),
            total_output_tokens=usage_data.get("total_output_tokens", 0),
            total_cost_usd=usage_data.get("total_cost_usd", "0"),
            avg_tokens_per_execution=usage_data.get("avg_tokens_per_execution", 0),
            by_provider=usage_data.get("by_provider", {})
        )

        return APIResponse(
            success=True,
            message=f"Workflow usage for last {days} days",
            data=workflow_usage
        )

    except Exception as e:
        logger.error(f"Failed to get workflow usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow usage"
        )


# ============================================================
# PRICING INFORMATION ENDPOINTS
# ============================================================

@router.get(
    "/pricing",
    response_model=APIResponse[List[RateCard]],
    summary="Get pricing",
    description="Returns current pricing for all supported models"
)
async def get_pricing():
    """
    Returns pricing information for all supported AI models.

    Useful for cost estimation before running workflows.
    """
    rate_cards = []

    for provider, models in RATE_CARDS.items():
        for model, rates in models.items():
            rate_cards.append(RateCard(
                provider=provider,
                model=model,
                input_cost_per_1k=rates["input"],
                output_cost_per_1k=rates["output"]
            ))

    return APIResponse(
        success=True,
        message=f"Pricing for {len(rate_cards)} models",
        data=rate_cards
    )


@router.post(
    "/estimate",
    response_model=APIResponse[Dict[str, Any]],
    summary="Estimate cost",
    description="Estimates cost for a given token count"
)
async def estimate_cost(
        provider: str = Query(..., description="AI provider (gemini, openai, etc.)"),
        model: str = Query(..., description="Model name"),
        input_tokens: int = Query(..., ge=0, description="Number of input tokens"),
        output_tokens: int = Query(..., ge=0, description="Number of output tokens")
):
    """
    Estimates cost for a given token count.

    Useful for budgeting and planning.
    """
    try:
        cost = CostCalculator.calculate(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        rates = CostCalculator.get_rate(provider, model)

        return APIResponse(
            success=True,
            message="Cost estimated",
            data={
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": str(cost),
                "rates": {
                    "input_per_1k": rates["input"],
                    "output_per_1k": rates["output"]
                }
            }
        )

    except Exception as e:
        logger.error(f"Failed to estimate cost: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to estimate cost: {str(e)}"
        )


# ============================================================
# PLAN MANAGEMENT ENDPOINTS
# ============================================================

@router.get(
    "/plans",
    response_model=APIResponse[List[PlanInfo]],
    summary="Get available plans",
    description="Returns information about available plans"
)
async def get_plans():
    """
    Returns information about available subscription plans.
    """
    from src.models.sql.workflow.usage import PLAN_LIMITS

    plans = []
    for plan_name, limits in PLAN_LIMITS.items():
        plans.append(PlanInfo(
            name=plan_name,
            monthly_token_limit=limits["monthly_token_limit"],
            monthly_execution_limit=limits["monthly_execution_limit"],
            monthly_cost_limit_usd=limits["monthly_cost_limit_usd"]
        ))

    return APIResponse(
        success=True,
        message=f"{len(plans)} plans available",
        data=plans
    )


# ============================================================
# ADMIN ENDPOINTS (Optional - Add proper admin auth)
# ============================================================

@router.post(
    "/admin/update-plan",
    response_model=APIResponse[Dict[str, Any]],
    summary="Update user plan (Admin)",
    description="Updates a user's subscription plan",
    include_in_schema=False  # Hide from public docs
)
async def admin_update_plan(
        user_id: UUID,
        new_plan: str = Query(..., description="New plan name (free, pro, enterprise)"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Admin endpoint to update a user's plan.

    Note: In production, add proper admin role verification.
    """
    # TODO: Add admin role check
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin access required")

    if new_plan not in ["free", "pro", "enterprise"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan. Must be: free, pro, or enterprise"
        )

    try:
        quota = await update_user_plan(db, user_id, new_plan)

        return APIResponse(
            success=True,
            message=f"User plan updated to {new_plan}",
            data={
                "user_id": str(user_id),
                "new_plan": new_plan,
                "limits": {
                    "tokens": quota.monthly_token_limit,
                    "executions": quota.monthly_execution_limit,
                    "cost_usd": quota.monthly_cost_limit_usd
                }
            }
        )

    except Exception as e:
        logger.error(f"Failed to update plan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update plan"
        )