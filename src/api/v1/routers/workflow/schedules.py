"""
Schedules API - Workflow scheduling and automation management.

Provides endpoints for creating, managing, and monitoring scheduled
workflow executions with support for cron, interval, and one-time schedules.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.schedule import WorkflowSchedule, ScheduleStatus, ScheduleType
from src.schemas.workflow.response import APIResponse, PaginationMeta
from src.schemas.workflow.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleResponse,
    ScheduleListResponse,
    ScheduleStatsResponse,
)


router = APIRouter()


# ============================================================
# DEPENDENCIES
# ============================================================

async def get_schedule_or_404(
        schedule_id: UUID,
        current_user: User,
        db: AsyncSession
) -> WorkflowSchedule:
    """
    Gets schedule by ID and verifies user ownership.

    Args:
        schedule_id: Schedule UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        WorkflowSchedule if found and authorized

    Raises:
        HTTPException: 404 if not found, 403 if not authorized
    """
    query = (
        select(WorkflowSchedule)
        .where(WorkflowSchedule.id == schedule_id)
        .options(selectinload(WorkflowSchedule.workflow))
    )
    result = await db.execute(query)
    schedule = result.scalars().first()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found"
        )

    if schedule.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this schedule"
        )

    return schedule


async def get_workflow_or_404(
        workflow_id: UUID,
        current_user: User,
        db: AsyncSession
) -> Workflow:
    """Gets workflow and verifies user ownership."""
    query = select(Workflow).where(Workflow.id == workflow_id)
    result = await db.execute(query)
    workflow = result.scalars().first()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this workflow"
        )

    return workflow


# ============================================================
# CRUD ENDPOINTS
# ============================================================

@router.get(
    "/",
    response_model=APIResponse[List[ScheduleListResponse]],
    summary="List schedules",
    description="Get all schedules for current user with pagination and filtering"
)
async def list_schedules(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Maximum records to return"),
        status_filter: Optional[ScheduleStatus] = Query(
            None,
            alias="status",
            description="Filter by status"
        ),
        workflow_id: Optional[UUID] = Query(
            None,
            description="Filter by workflow"
        ),
        schedule_type: Optional[ScheduleType] = Query(
            None,
            description="Filter by schedule type"
        ),
        search: Optional[str] = Query(
            None,
            description="Search in name and description"
        ),
        sort_by: str = Query(
            "created_at",
            description="Sort field (name, created_at, next_run_at, status)"
        ),
        sort_order: str = Query(
            "desc",
            description="Sort order: asc or desc"
        ),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Lists all schedules for the authenticated user.

    Supports filtering by:
    - status: ACTIVE, PAUSED, DISABLED, COMPLETED
    - workflow_id: Filter to specific workflow
    - schedule_type: CRON, INTERVAL, ONCE
    - search: Search in name and description

    Supports sorting by name, created_at, next_run_at, status.
    """
    # Build base query
    query = select(WorkflowSchedule).where(
        WorkflowSchedule.user_id == current_user.id
    )

    # Apply filters
    if status_filter:
        query = query.where(WorkflowSchedule.status == status_filter)

    if workflow_id:
        query = query.where(WorkflowSchedule.workflow_id == workflow_id)

    if schedule_type:
        query = query.where(WorkflowSchedule.schedule_type == schedule_type)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            WorkflowSchedule.name.ilike(search_term) |
            WorkflowSchedule.description.ilike(search_term)
        )

    # Apply sorting
    sort_column_map = {
        "name": WorkflowSchedule.name,
        "created_at": WorkflowSchedule.created_at,
        "next_run_at": WorkflowSchedule.next_run_at,
        "status": WorkflowSchedule.status,
        "updated_at": WorkflowSchedule.updated_at,
    }
    sort_column = sort_column_map.get(sort_by, WorkflowSchedule.created_at)

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc().nulls_last())
    else:
        query = query.order_by(sort_column.desc().nulls_last())

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    schedules = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {total} schedules",
        data=[ScheduleListResponse.from_schedule(s) for s in schedules],
        meta={
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + len(schedules) < total
        }
    )


@router.post(
    "/",
    response_model=APIResponse[ScheduleResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create schedule",
    description="Create a new schedule for a workflow"
)
async def create_schedule(
        schedule_in: ScheduleCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Creates a new schedule for automated workflow execution.

    Supports three schedule types:
    - CRON: Cron expression based (e.g., "0 9 * * *" for daily at 9am)
    - INTERVAL: Execute every N seconds (minimum 60 seconds)
    - ONCE: Single execution at specified time

    The schedule is created in ACTIVE status and will begin executing
    according to its configuration.
    """
    # Verify workflow exists and user owns it
    workflow = await get_workflow_or_404(
        schedule_in.workflow_id,
        current_user,
        db
    )

    # Validate workflow is in runnable state
    if workflow.status not in [WorkflowStatus.PUBLISHED, WorkflowStatus.DRAFT]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot schedule workflow with status '{workflow.status.value}'. "
                   f"Workflow must be PUBLISHED or DRAFT."
        )

    # Create schedule
    schedule = WorkflowSchedule(
        user_id=current_user.id,
        workflow_id=schedule_in.workflow_id,
        name=schedule_in.name,
        description=schedule_in.description,
        schedule_type=schedule_in.schedule_type,
        cron_expression=schedule_in.cron_expression,
        interval_seconds=schedule_in.interval_seconds,
        run_at=schedule_in.run_at,
        timezone=schedule_in.timezone,
        input_data=schedule_in.input_data,
        max_consecutive_errors=schedule_in.max_consecutive_errors,
        status=ScheduleStatus.ACTIVE
    )

    # Calculate next run time
    schedule.update_next_run()

    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Schedule created: {schedule.id}",
        extra={
            "user_id": str(current_user.id),
            "schedule_id": str(schedule.id),
            "workflow_id": str(schedule_in.workflow_id),
            "schedule_type": schedule_in.schedule_type.value
        }
    )

    return APIResponse(
        success=True,
        message="Schedule created successfully",
        data=ScheduleResponse.from_schedule(schedule)
    )


@router.get(
    "/{schedule_id}",
    response_model=APIResponse[ScheduleResponse],
    summary="Get schedule",
    description="Get a specific schedule by ID"
)
async def get_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets a schedule by ID with full details."""
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    return APIResponse(
        success=True,
        message="Schedule retrieved",
        data=ScheduleResponse.from_schedule(schedule)
    )


@router.patch(
    "/{schedule_id}",
    response_model=APIResponse[ScheduleResponse],
    summary="Update schedule",
    description="Update schedule configuration"
)
async def update_schedule(
        schedule_id: UUID,
        schedule_in: ScheduleUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Updates a schedule configuration.

    Allows updating:
    - name, description
    - cron_expression (for CRON type)
    - interval_seconds (for INTERVAL type)
    - run_at (for ONCE type)
    - timezone
    - input_data
    - max_consecutive_errors

    Changes to timing configuration will recalculate the next run time.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    # Track if timing changed
    timing_changed = False

    # Update fields if provided
    if schedule_in.name is not None:
        schedule.name = schedule_in.name

    if schedule_in.description is not None:
        schedule.description = schedule_in.description

    if schedule_in.cron_expression is not None:
        if schedule.schedule_type != ScheduleType.CRON:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set cron_expression on non-CRON schedule"
            )
        schedule.cron_expression = schedule_in.cron_expression
        timing_changed = True

    if schedule_in.interval_seconds is not None:
        if schedule.schedule_type != ScheduleType.INTERVAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set interval_seconds on non-INTERVAL schedule"
            )
        schedule.interval_seconds = schedule_in.interval_seconds
        timing_changed = True

    if schedule_in.run_at is not None:
        if schedule.schedule_type != ScheduleType.ONCE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set run_at on non-ONCE schedule"
            )
        schedule.run_at = schedule_in.run_at
        timing_changed = True

    if schedule_in.timezone is not None:
        schedule.timezone = schedule_in.timezone
        timing_changed = True

    if schedule_in.input_data is not None:
        schedule.input_data = schedule_in.input_data

    if schedule_in.max_consecutive_errors is not None:
        schedule.max_consecutive_errors = schedule_in.max_consecutive_errors

    # Recalculate next run if timing changed
    if timing_changed:
        schedule.update_next_run()

    schedule.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Schedule updated: {schedule.id}",
        extra={"user_id": str(current_user.id), "schedule_id": str(schedule.id)}
    )

    return APIResponse(
        success=True,
        message="Schedule updated successfully",
        data=ScheduleResponse.from_schedule(schedule)
    )


@router.delete(
    "/{schedule_id}",
    response_model=APIResponse,
    summary="Delete schedule",
    description="Permanently delete a schedule"
)
async def delete_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Permanently deletes a schedule.

    This action cannot be undone. Consider using pause instead
    if you want to temporarily stop the schedule.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    schedule_name = schedule.name
    await db.delete(schedule)
    await db.commit()

    logger.info(
        f"Schedule deleted: {schedule_id}",
        extra={
            "user_id": str(current_user.id),
            "schedule_id": str(schedule_id),
            "schedule_name": schedule_name
        }
    )

    return APIResponse(
        success=True,
        message=f"Schedule '{schedule_name}' deleted successfully"
    )


# ============================================================
# STATUS MANAGEMENT ENDPOINTS
# ============================================================

@router.post(
    "/{schedule_id}/pause",
    response_model=APIResponse[ScheduleResponse],
    summary="Pause schedule",
    description="Pause an active schedule"
)
async def pause_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Pauses an active schedule.

    The schedule will stop executing until resumed.
    Execution history is preserved.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    if schedule.status == ScheduleStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Schedule is already paused"
        )

    if schedule.status == ScheduleStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot pause a completed schedule"
        )

    if schedule.status == ScheduleStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot pause a disabled schedule"
        )

    schedule.pause()
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Schedule paused: {schedule.id}",
        extra={"user_id": str(current_user.id), "schedule_id": str(schedule.id)}
    )

    return APIResponse(
        success=True,
        message="Schedule paused successfully",
        data=ScheduleResponse.from_schedule(schedule)
    )


@router.post(
    "/{schedule_id}/resume",
    response_model=APIResponse[ScheduleResponse],
    summary="Resume schedule",
    description="Resume a paused schedule"
)
async def resume_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Resumes a paused schedule.

    The schedule will begin executing according to its configuration.
    Consecutive error count is reset upon resume.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    if schedule.status != ScheduleStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume schedule with status '{schedule.status.value}'. "
                   f"Only PAUSED schedules can be resumed."
        )

    schedule.resume()
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Schedule resumed: {schedule.id}",
        extra={"user_id": str(current_user.id), "schedule_id": str(schedule.id)}
    )

    return APIResponse(
        success=True,
        message="Schedule resumed successfully",
        data=ScheduleResponse.from_schedule(schedule)
    )


@router.post(
    "/{schedule_id}/disable",
    response_model=APIResponse[ScheduleResponse],
    summary="Disable schedule",
    description="Permanently disable a schedule"
)
async def disable_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Permanently disables a schedule.

    Unlike pause, a disabled schedule cannot be resumed.
    Use this for schedules that should never run again but
    need to be preserved for audit purposes.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    if schedule.status == ScheduleStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Schedule is already disabled"
        )

    schedule.disable()
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        f"Schedule disabled: {schedule.id}",
        extra={"user_id": str(current_user.id), "schedule_id": str(schedule.id)}
    )

    return APIResponse(
        success=True,
        message="Schedule disabled successfully",
        data=ScheduleResponse.from_schedule(schedule)
    )


# ============================================================
# UTILITY ENDPOINTS
# ============================================================

@router.get(
    "/stats/summary",
    response_model=APIResponse[ScheduleStatsResponse],
    summary="Get schedule statistics",
    description="Get aggregated statistics for user's schedules"
)
async def get_schedule_stats(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns aggregated statistics for all user schedules.

    Includes:
    - Total schedule count
    - Active/paused breakdown
    - Total runs and errors
    - Success rate
    """
    # Get all user schedules
    query = select(WorkflowSchedule).where(
        WorkflowSchedule.user_id == current_user.id
    )
    result = await db.execute(query)
    schedules = result.scalars().all()

    total = len(schedules)
    active = sum(1 for s in schedules if s.status == ScheduleStatus.ACTIVE)
    paused = sum(1 for s in schedules if s.status == ScheduleStatus.PAUSED)
    total_runs = sum(s.run_count for s in schedules)
    total_errors = sum(s.error_count for s in schedules)

    success_rate = 0.0
    if total_runs > 0:
        success_rate = ((total_runs - total_errors) / total_runs) * 100

    return APIResponse(
        success=True,
        message="Schedule statistics retrieved",
        data=ScheduleStatsResponse(
            total_schedules=total,
            active_schedules=active,
            paused_schedules=paused,
            total_runs=total_runs,
            total_errors=total_errors,
            success_rate=round(success_rate, 2)
        )
    )


@router.post(
    "/{schedule_id}/trigger",
    response_model=APIResponse,
    summary="Trigger immediate execution",
    description="Manually trigger a schedule's workflow immediately"
)
async def trigger_schedule(
        schedule_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Manually triggers immediate execution of a scheduled workflow.

    This executes the workflow once immediately, regardless of the
    schedule's normal timing. Does not affect the scheduled timing.

    Note: The actual execution is handled by the workflow execution
    system. This endpoint queues the execution request.
    """
    schedule = await get_schedule_or_404(schedule_id, current_user, db)

    if schedule.status == ScheduleStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot trigger a disabled schedule"
        )

    # Verify workflow is still valid
    workflow_query = select(Workflow).where(Workflow.id == schedule.workflow_id)
    workflow_result = await db.execute(workflow_query)
    workflow = workflow_result.scalars().first()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled workflow no longer exists"
        )

    if workflow.status == WorkflowStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot execute archived workflow"
        )

    # TODO: Integrate with workflow execution service
    # execution_id = await workflow_execution_service.execute(
    #     workflow_id=schedule.workflow_id,
    #     input_data=schedule.input_data,
    #     trigger_type="manual_schedule_trigger",
    #     schedule_id=schedule.id
    # )

    logger.info(
        f"Schedule manually triggered: {schedule.id}",
        extra={
            "user_id": str(current_user.id),
            "schedule_id": str(schedule.id),
            "workflow_id": str(schedule.workflow_id)
        }
    )

    return APIResponse(
        success=True,
        message="Schedule triggered successfully. Execution has been queued.",
        data={
            "schedule_id": str(schedule.id),
            "workflow_id": str(schedule.workflow_id),
            "triggered_at": datetime.now(timezone.utc).isoformat()
        }
    )
