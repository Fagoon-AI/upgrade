from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, extract, text
from sqlalchemy.orm import selectinload
from loguru import logger
from pydantic import BaseModel, Field

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus, NodeExecutionTrace
from src.dao.workflow_dao import WorkflowDAO
from src.schemas.workflow.execution import (
    ExecutionResponse,
    ExecutionStatusResponse,
    NodeTraceResponse,
    ExecutionTimelineResponse
)
from src.schemas.workflow.response import APIResponse
from src.services.workflow.cost_tracking import check_and_enforce_quota, QuotaExceededError



router = APIRouter()


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ExecutionRunRequest(BaseModel):
    """Request schema for running a workflow."""
    initial_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Initial input data for the workflow"
    )
    async_execution: bool = Field(
        default=True,
        description="Run asynchronously (recommended)"
    )
    single_node_id: Optional[str] = Field(
        default=None,
        description="Optional specific node to execute in isolation (Play Button)"
    )


class ExecutionResumeRequest(BaseModel):
    """Request schema for resuming an execution."""
    node_id: str = Field(..., description="Node ID to resume from")
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional input for resumption"
    )


class BulkStatusRequest(BaseModel):
    """Request schema for bulk status check."""
    execution_ids: List[UUID] = Field(
        ...,
        max_length=50,
        description="List of execution IDs to check"
    )


# ============================================================
# HELPERS
# ============================================================

async def get_execution_with_auth(
        execution_id: UUID,
        current_user: User,
        db: AsyncSession
) -> tuple[WorkflowExecution, Workflow]:
    """Gets execution with authorization check."""
    query = (
        select(WorkflowExecution, Workflow)
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(WorkflowExecution.id == execution_id)
    )
    result = await db.execute(query)
    record = result.first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    execution, workflow = record

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this execution"
        )

    return execution, workflow


# ============================================================
# EXECUTION LIFECYCLE
# ============================================================

@router.post(
    "/{workflow_id}/run",
    response_model=APIResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run workflow",
    description="Start a new workflow execution"
)
async def run_workflow(
        workflow_id: UUID,
        request: Request,
        body: ExecutionRunRequest = Body(default=ExecutionRunRequest()),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Starts a new workflow execution."""
    try:
        await check_and_enforce_quota(db, current_user.id)
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=e.to_dict())
    # Get workflow
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
            detail="Not authorized to run this workflow"
        )

    # Check workflow is runnable
    if not workflow.active_version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow has no active version. Save the workflow first."
        )

    if workflow.status == "ARCHIVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot run archived workflow"
        )

    # Create execution record
    new_execution = WorkflowExecution(
        workflow_id=workflow.id,
        version_id=workflow.active_version_id,
        status=ExecutionStatus.PENDING,
        trigger_type="MANUAL",
        graph_snapshot=workflow.graph_definition,
        context_data={}
    )

    db.add(new_execution)
    await db.commit()
    await db.refresh(new_execution)

    logger.info(
        f"Execution created: {new_execution.id}",
        extra={
            "user_id": str(current_user.id),
            "workflow_id": str(workflow.id),
            "execution_id": str(new_execution.id)
        }
    )

    # Dispatch to worker via dual-mode queue abstraction
    if body.async_execution:
        request.app.state.queue.enqueue(
            "execute_workflow_task",
            execution_id=str(new_execution.id),
            workflow_id=str(workflow.id),
            initial_input=body.initial_input,
            single_node_id=body.single_node_id
        )

        return APIResponse(
            success=True,
            message="Workflow execution started",
            data={
                "execution_id": str(new_execution.id),
                "status": "PENDING",
                "async": True
            }
        )
    else:
        # Synchronous execution (not recommended for production)
        request.app.state.queue.enqueue(
            "execute_workflow_task",
            execution_id=str(new_execution.id),
            workflow_id=str(workflow.id),
            initial_input=body.initial_input,
            single_node_id=body.single_node_id
        )

        return APIResponse(
            success=True,
            message="Workflow execution queued",
            data={
                "execution_id": str(new_execution.id),
                "status": "PENDING"
            }
        )


@router.get(
    "/{execution_id}/status",
    response_model=APIResponse[ExecutionStatusResponse],
    summary="Get execution status",
    description="Get current status of an execution"
)
async def get_execution_status(
        execution_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets execution status."""
    execution, workflow = await get_execution_with_auth(execution_id, current_user, db)

    # Get error from context if failed
    error = None
    if execution.status == ExecutionStatus.FAILED:
        error = execution.context_data.get("error") if execution.context_data else None

    response_data = ExecutionStatusResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        trigger_type=execution.trigger_type,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        results=execution.results if execution.status == ExecutionStatus.COMPLETED else None,
        error=error
    )

    return APIResponse(
        success=True,
        message=f"Status: {execution.status.value}",
        data=response_data
    )


@router.post(
    "/{execution_id}/cancel",
    response_model=APIResponse,
    summary="Cancel execution",
    description="Cancel a running execution"
)
async def cancel_execution(
        execution_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Cancels a running execution."""
    execution, workflow = await get_execution_with_auth(execution_id, current_user, db)

    if execution.status not in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution with status: {execution.status.value}"
        )

    # Update status
    execution.status = ExecutionStatus.FAILED
    execution.finished_at = datetime.now(timezone.utc)
    if not execution.context_data:
        execution.context_data = {}
    execution.context_data["error"] = "Cancelled by user"

    await db.commit()

    logger.info(
        f"Execution cancelled: {execution_id}",
        extra={"user_id": str(current_user.id)}
    )

    return APIResponse(
        success=True,
        message="Execution cancelled"
    )


@router.post(
    "/{execution_id}/resume",
    response_model=APIResponse,
    summary="Resume execution",
    description="Resume a paused execution from a specific node"
)
async def resume_execution(
        execution_id: UUID,
        body: ExecutionResumeRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Resumes a paused execution."""
    execution, workflow = await get_execution_with_auth(execution_id, current_user, db)

    if execution.status != ExecutionStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only paused executions can be resumed"
        )

    # Validate node exists in graph
    graph = execution.graph_snapshot or workflow.graph_definition
    node_ids = [n["id"] for n in graph.get("nodes", [])]

    if body.node_id not in node_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Node '{body.node_id}' not found in workflow"
        )

    # Update status
    execution.status = ExecutionStatus.PENDING
    await db.commit()

    # Dispatch resume task via dual-mode queue abstraction
    request.app.state.queue.enqueue(
        "execute_workflow_task",
        execution_id=str(execution.id),
        workflow_id=str(execution.workflow_id),
        initial_input=body.input_data,
        resume_node_id=body.node_id
    )

    logger.info(
        f"Execution resumed: {execution_id} from node {body.node_id}",
        extra={"user_id": str(current_user.id)}
    )

    return APIResponse(
        success=True,
        message="Execution resumed",
        data={
            "execution_id": str(execution_id),
            "resumed_from": body.node_id,
            "status": "PENDING"
        }
    )


@router.post(
    "/{execution_id}/retry",
    response_model=APIResponse,
    summary="Retry execution",
    description="Retry a failed execution from the beginning"
)
async def retry_execution(
        execution_id: UUID,
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Retries a failed execution."""
    execution, workflow = await get_execution_with_auth(execution_id, current_user, db)

    if execution.status != ExecutionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed executions can be retried"
        )

    # Create new execution
    new_execution = WorkflowExecution(
        workflow_id=workflow.id,
        version_id=execution.version_id,
        status=ExecutionStatus.PENDING,
        trigger_type="RETRY",
        graph_snapshot=execution.graph_snapshot,
        context_data={}
    )

    db.add(new_execution)
    await db.commit()
    await db.refresh(new_execution)

    # Get original input from context
    original_input = {}
    if execution.context_data:
        start_output = execution.context_data.get("start-1", {})
        original_input = start_output.get("initial_input", {})

    # Dispatch via dual-mode queue abstraction
    request.app.state.queue.enqueue(
        "execute_workflow_task",
        execution_id=str(new_execution.id),
        workflow_id=str(workflow.id),
        initial_input=original_input
    )

    return APIResponse(
        success=True,
        message="Execution retry started",
        data={
            "original_execution_id": str(execution_id),
            "new_execution_id": str(new_execution.id),
            "status": "PENDING"
        }
    )


# ============================================================
# BULK OPERATIONS
# ============================================================

@router.post(
    "/bulk/status",
    response_model=APIResponse[List[dict]],
    summary="Bulk status check",
    description="Check status of multiple executions at once"
)
async def bulk_status_check(
        body: BulkStatusRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Checks status of multiple executions."""
    # Query all executions
    query = (
        select(WorkflowExecution, Workflow)
        .join(Workflow)
        .where(
            and_(
                WorkflowExecution.id.in_(body.execution_ids),
                Workflow.user_id == current_user.id
            )
        )
    )

    result = await db.execute(query)
    records = result.all()

    # Build response
    statuses = []
    found_ids = set()

    for execution, workflow in records:
        found_ids.add(execution.id)
        statuses.append({
            "execution_id": str(execution.id),
            "workflow_id": str(execution.workflow_id),
            "status": execution.status.value,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None
        })

    # Add not found IDs
    for exec_id in body.execution_ids:
        if exec_id not in found_ids:
            statuses.append({
                "execution_id": str(exec_id),
                "status": "NOT_FOUND"
            })

    return APIResponse(
        success=True,
        message=f"Retrieved status for {len(statuses)} executions",
        data=statuses
    )


# ============================================================
# OBSERVABILITY
# ============================================================

@router.get(
    "/{execution_id}/timeline",
    response_model=APIResponse[ExecutionTimelineResponse],
    summary="Get execution timeline",
    description="Get detailed node-by-node execution trace"
)
async def get_execution_timeline(
        execution_id: UUID,
        include_inputs: bool = Query(True, description="Include node inputs in response"),
        include_outputs: bool = Query(True, description="Include node outputs in response"),
        status_filter: Optional[str] = Query(None, description="Filter traces by status"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets detailed execution timeline."""
    execution, workflow = await get_execution_with_auth(execution_id, current_user, db)

    # Build trace query
    query = (
        select(NodeExecutionTrace)
        .where(NodeExecutionTrace.execution_id == execution_id)
    )

    if status_filter:
        query = query.where(NodeExecutionTrace.status == status_filter.upper())

    query = query.order_by(NodeExecutionTrace.created_at.asc())

    result = await db.execute(query)
    traces = result.scalars().all()

    # Build trace responses
    trace_responses = []
    for t in traces:
        trace_data = NodeTraceResponse(
            id=t.id,
            node_id=t.node_id,
            node_type=t.node_type,
            status=t.status,
            duration_ms=t.duration_ms,
            created_at=t.created_at,
            inputs=t.inputs if include_inputs else None,
            outputs=t.outputs if include_outputs else None,
            error_message=t.error_message
        )
        trace_responses.append(trace_data)

    # Calculate total duration and counts
    total_duration = sum(t.duration_ms for t in traces)
    success_count = sum(1 for t in traces if t.status == "SUCCESS")
    failed_count = sum(1 for t in traces if t.status == "FAILED")

    return APIResponse(
        success=True,
        message="Timeline retrieved",
        data=ExecutionTimelineResponse(
            execution_id=execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            total_duration_ms=total_duration,
            node_count=len(traces),
            success_count=success_count,
            failed_count=failed_count,
            traces=trace_responses
        )
    )


@router.get(
    "/node-trace/{trace_id}",
    response_model=APIResponse[NodeTraceResponse],
    summary="Get node trace detail",
    description="Get detailed information about a specific node execution"
)
async def get_node_trace_detail(
        trace_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets detailed node trace."""
    query = (
        select(NodeExecutionTrace, WorkflowExecution, Workflow)
        .join(WorkflowExecution, NodeExecutionTrace.execution_id == WorkflowExecution.id)
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(NodeExecutionTrace.id == trace_id)
    )

    result = await db.execute(query)
    record = result.first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found"
        )

    trace, execution, workflow = record

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this trace"
        )

    return APIResponse(
        success=True,
        message="Trace detail retrieved",
        data=NodeTraceResponse.model_validate(trace)
    )


# ============================================================
# LISTING & SEARCH
# ============================================================

@router.get(
    "",
    response_model=APIResponse[List[ExecutionResponse]],
    summary="List all executions",
    description="List executions across all workflows with filtering"
)
async def list_all_executions(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        workflow_id: Optional[UUID] = Query(None, description="Filter by workflow"),
        status_filter: Optional[ExecutionStatus] = Query(None, alias="status"),
        trigger_type: Optional[str] = Query(None, description="Filter by trigger type"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Lists all executions for current user."""
    # Build query
    query = (
        select(WorkflowExecution)
        .join(Workflow)
        .where(Workflow.user_id == current_user.id)
    )

    if workflow_id:
        query = query.where(WorkflowExecution.workflow_id == workflow_id)

    if status_filter:
        query = query.where(WorkflowExecution.status == status_filter)

    if trigger_type:
        query = query.where(WorkflowExecution.trigger_type == trigger_type.upper())

    query = query.order_by(WorkflowExecution.started_at.desc())

    # Get total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    executions = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {total} executions",
        data=[ExecutionResponse.model_validate(e) for e in executions],
        meta={
            "total": total,
            "skip": skip,
            "limit": limit
        }
    )


# ============================================================
# ANALYTICS & AGGREGATION
# ============================================================

class AnalyticsPeriod(str):
    """Time periods for analytics aggregation."""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ExecutionAnalyticsResponse(BaseModel):
    """Response schema for execution analytics."""
    period_start: datetime
    period_end: datetime
    total_executions: int
    successful_executions: int
    failed_executions: int
    pending_executions: int
    running_executions: int
    paused_executions: int
    success_rate: float
    avg_duration_ms: Optional[float]
    total_duration_ms: int
    executions_by_status: Dict[str, int]
    executions_by_trigger: Dict[str, int]
    executions_by_workflow: Dict[str, int]
    hourly_distribution: List[Dict[str, Any]]
    top_failing_workflows: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]


@router.get(
    "/analytics",
    response_model=APIResponse[ExecutionAnalyticsResponse],
    summary="Get execution analytics",
    description="Get aggregated execution statistics for dashboard"
)
async def get_execution_analytics(
    period: str = Query("day", description="Time period: hour, day, week, month"),
    workflow_id: Optional[UUID] = Query(None, description="Filter by specific workflow"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns aggregated execution analytics.

    Provides dashboard-ready statistics including:
    - Success/failure rates
    - Execution counts by status and trigger type
    - Average duration metrics
    - Hourly distribution for trend analysis
    - Top failing workflows for issue identification
    - Recent errors for quick debugging
    """
    # Calculate period bounds
    now = datetime.now(timezone.utc)
    period_map = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30)
    }

    if period not in period_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period. Must be one of: {list(period_map.keys())}"
        )

    period_start = now - period_map[period]
    period_end = now

    # Base query filters
    base_filters = [
        Workflow.user_id == current_user.id,
        WorkflowExecution.started_at >= period_start,
        WorkflowExecution.started_at <= period_end
    ]

    if workflow_id:
        base_filters.append(WorkflowExecution.workflow_id == workflow_id)

    # Query 1: Aggregate counts by status
    status_query = (
        select(
            WorkflowExecution.status,
            func.count(WorkflowExecution.id).label("count")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(*base_filters))
        .group_by(WorkflowExecution.status)
    )

    status_result = await db.execute(status_query)
    status_counts = {row.status.value: row.count for row in status_result.all()}

    # Calculate totals
    total_executions = sum(status_counts.values())
    successful = status_counts.get("COMPLETED", 0)
    failed = status_counts.get("FAILED", 0)
    pending = status_counts.get("PENDING", 0)
    running = status_counts.get("RUNNING", 0)
    paused = status_counts.get("PAUSED", 0)

    success_rate = (successful / total_executions * 100) if total_executions > 0 else 0.0

    # Query 2: Aggregate counts by trigger type
    trigger_query = (
        select(
            WorkflowExecution.trigger_type,
            func.count(WorkflowExecution.id).label("count")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(*base_filters))
        .group_by(WorkflowExecution.trigger_type)
    )

    trigger_result = await db.execute(trigger_query)
    trigger_counts = {row.trigger_type or "UNKNOWN": row.count for row in trigger_result.all()}

    # Query 3: Aggregate counts by workflow
    workflow_query = (
        select(
            WorkflowExecution.workflow_id,
            Workflow.name,
            func.count(WorkflowExecution.id).label("count")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(*base_filters))
        .group_by(WorkflowExecution.workflow_id, Workflow.name)
        .order_by(func.count(WorkflowExecution.id).desc())
        .limit(10)
    )

    workflow_result = await db.execute(workflow_query)
    workflow_counts = {
        str(row.workflow_id): {
            "name": row.name,
            "count": row.count
        }
        for row in workflow_result.all()
    }

    # Query 4: Duration statistics for completed executions
    duration_query = (
        select(
            func.avg(
                extract('epoch', WorkflowExecution.finished_at) -
                extract('epoch', WorkflowExecution.started_at)
            ).label("avg_duration"),
            func.sum(
                extract('epoch', WorkflowExecution.finished_at) -
                extract('epoch', WorkflowExecution.started_at)
            ).label("total_duration")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(
            *base_filters,
            WorkflowExecution.status == ExecutionStatus.COMPLETED,
            WorkflowExecution.finished_at.isnot(None)
        ))
    )

    duration_result = await db.execute(duration_query)
    duration_row = duration_result.first()
    avg_duration_ms = int(duration_row.avg_duration * 1000) if duration_row.avg_duration else None
    total_duration_ms = int(duration_row.total_duration * 1000) if duration_row.total_duration else 0

    # Query 5: Hourly distribution (for trend charts)
    hourly_query = (
        select(
            extract('hour', WorkflowExecution.started_at).label("hour"),
            func.count(WorkflowExecution.id).label("count"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.COMPLETED, 1), else_=0)).label("success"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.FAILED, 1), else_=0)).label("failed")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(*base_filters))
        .group_by(extract('hour', WorkflowExecution.started_at))
        .order_by(extract('hour', WorkflowExecution.started_at))
    )

    hourly_result = await db.execute(hourly_query)
    hourly_distribution = [
        {
            "hour": int(row.hour),
            "total": row.count,
            "success": row.success or 0,
            "failed": row.failed or 0
        }
        for row in hourly_result.all()
    ]

    # Query 6: Top failing workflows
    failing_query = (
        select(
            WorkflowExecution.workflow_id,
            Workflow.name,
            func.count(WorkflowExecution.id).label("failure_count")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(
            *base_filters,
            WorkflowExecution.status == ExecutionStatus.FAILED
        ))
        .group_by(WorkflowExecution.workflow_id, Workflow.name)
        .order_by(func.count(WorkflowExecution.id).desc())
        .limit(5)
    )

    failing_result = await db.execute(failing_query)
    top_failing = [
        {
            "workflow_id": str(row.workflow_id),
            "workflow_name": row.name,
            "failure_count": row.failure_count
        }
        for row in failing_result.all()
    ]

    # Query 7: Recent errors
    errors_query = (
        select(
            WorkflowExecution.id,
            WorkflowExecution.workflow_id,
            Workflow.name.label("workflow_name"),
            WorkflowExecution.started_at,
            WorkflowExecution.context_data
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(
            *base_filters,
            WorkflowExecution.status == ExecutionStatus.FAILED
        ))
        .order_by(WorkflowExecution.started_at.desc())
        .limit(10)
    )

    errors_result = await db.execute(errors_query)
    recent_errors = []
    for row in errors_result.all():
        error_msg = None
        if row.context_data and isinstance(row.context_data, dict):
            error_msg = row.context_data.get("error")

        recent_errors.append({
            "execution_id": str(row.id),
            "workflow_id": str(row.workflow_id),
            "workflow_name": row.workflow_name,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "error": error_msg or "Unknown error"
        })

    logger.info(
        f"Analytics retrieved for user {current_user.id}",
        extra={
            "period": period,
            "total_executions": total_executions,
            "success_rate": success_rate
        }
    )

    return APIResponse(
        success=True,
        message=f"Analytics for {period} period",
        data=ExecutionAnalyticsResponse(
            period_start=period_start,
            period_end=period_end,
            total_executions=total_executions,
            successful_executions=successful,
            failed_executions=failed,
            pending_executions=pending,
            running_executions=running,
            paused_executions=paused,
            success_rate=round(success_rate, 2),
            avg_duration_ms=avg_duration_ms,
            total_duration_ms=total_duration_ms,
            executions_by_status=status_counts,
            executions_by_trigger=trigger_counts,
            executions_by_workflow={k: v["count"] for k, v in workflow_counts.items()},
            hourly_distribution=hourly_distribution,
            top_failing_workflows=top_failing,
            recent_errors=recent_errors
        )
    )


@router.get(
    "/analytics/summary",
    response_model=APIResponse,
    summary="Get quick analytics summary",
    description="Get a lightweight analytics summary for header/sidebar widgets"
)
async def get_analytics_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a lightweight analytics summary.

    Optimized for quick loading in UI widgets:
    - Today's execution count
    - Success rate
    - Active workflows
    - Running executions
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's stats
    today_query = (
        select(
            func.count(WorkflowExecution.id).label("total"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.COMPLETED, 1), else_=0)).label("success"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.RUNNING, 1), else_=0)).label("running")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(
            Workflow.user_id == current_user.id,
            WorkflowExecution.started_at >= today_start
        ))
    )

    result = await db.execute(today_query)
    row = result.first()

    total_today = row.total or 0
    success_today = row.success or 0
    running_count = row.running or 0

    success_rate = (success_today / total_today * 100) if total_today > 0 else 0.0

    # Active workflows count
    workflow_count_query = (
        select(func.count(Workflow.id))
        .where(and_(
            Workflow.user_id == current_user.id,
            Workflow.status == "ACTIVE"
        ))
    )

    workflow_result = await db.execute(workflow_count_query)
    active_workflows = workflow_result.scalar() or 0

    return APIResponse(
        success=True,
        message="Analytics summary",
        data={
            "today": {
                "total_executions": total_today,
                "successful": success_today,
                "success_rate": round(success_rate, 1)
            },
            "running_executions": running_count,
            "active_workflows": active_workflows
        }
    )


@router.get(
    "/analytics/trends",
    response_model=APIResponse,
    summary="Get execution trends",
    description="Get daily execution trends for the past 30 days"
)
async def get_execution_trends(
    workflow_id: Optional[UUID] = Query(None, description="Filter by specific workflow"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns daily execution trends for the past 30 days.

    Useful for:
    - Line charts showing execution volume over time
    - Success rate trend analysis
    - Identifying patterns and anomalies
    """
    period_start = datetime.now(timezone.utc) - timedelta(days=30)

    base_filters = [
        Workflow.user_id == current_user.id,
        WorkflowExecution.started_at >= period_start
    ]

    if workflow_id:
        base_filters.append(WorkflowExecution.workflow_id == workflow_id)

    # Daily aggregation using date truncation
    daily_query = (
        select(
            func.date_trunc('day', WorkflowExecution.started_at).label("date"),
            func.count(WorkflowExecution.id).label("total"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.COMPLETED, 1), else_=0)).label("success"),
            func.sum(case((WorkflowExecution.status == ExecutionStatus.FAILED, 1), else_=0)).label("failed")
        )
        .join(Workflow, WorkflowExecution.workflow_id == Workflow.id)
        .where(and_(*base_filters))
        .group_by(func.date_trunc('day', WorkflowExecution.started_at))
        .order_by(func.date_trunc('day', WorkflowExecution.started_at))
    )

    result = await db.execute(daily_query)
    rows = result.all()

    # Build trend data with zero-fill for missing days
    trend_data = []
    date_map = {row.date.date(): row for row in rows}

    current_date = period_start.date()
    end_date = datetime.now(timezone.utc).date()

    while current_date <= end_date:
        if current_date in date_map:
            row = date_map[current_date]
            total = row.total
            success = row.success or 0
            failed = row.failed or 0
        else:
            total = 0
            success = 0
            failed = 0

        success_rate = (success / total * 100) if total > 0 else 0.0

        trend_data.append({
            "date": current_date.isoformat(),
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": round(success_rate, 1)
        })

        current_date += timedelta(days=1)

    return APIResponse(
        success=True,
        message="30-day execution trends",
        data={
            "period_days": 30,
            "trends": trend_data
        }
    )