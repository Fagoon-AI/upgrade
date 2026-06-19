"""
Workflow Scheduler Tasks.

Celery tasks for processing workflow schedules.
"""

import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from loguru import logger

from src.core.database import get_database_manager
from src.models.sql.workflow.schedule import WorkflowSchedule, ScheduleStatus, ScheduleType
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus


# ============================================================
# CONFIGURATION
# ============================================================

# How far ahead to look for schedules (prevents missing schedules due to timing)
SCHEDULE_LOOKAHEAD_SECONDS = 60

# Maximum schedules to process per tick
MAX_SCHEDULES_PER_TICK = 100

# Minimum interval between runs (prevents runaway schedules)
MIN_INTERVAL_SECONDS = 60


# ============================================================
# MAIN SCHEDULER TASK (CELERY-FREE)
# ============================================================

def process_due_schedules_task() -> Dict[str, Any]:
    """
    Main scheduler task - checks for due schedules and triggers workflow executions.

    This task should run frequently (e.g., every minute via Celery Beat).
    It finds all schedules that are due and triggers their workflows.

    Returns:
        Summary of processed schedules
    """
    logger.info("Processing due schedules")

    try:
        result = asyncio.run(_process_due_schedules_async())
        return result
    except Exception as e:
        logger.error(f"Scheduler task failed: {e}\n{traceback.format_exc()}")
        raise


async def _process_due_schedules_async() -> Dict[str, Any]:
    """
    Async implementation of schedule processing.

    Returns:
        Processing summary
    """
    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(seconds=SCHEDULE_LOOKAHEAD_SECONDS)

        # Find due schedules
        result = await db.execute(
            select(WorkflowSchedule)
            .options(selectinload(WorkflowSchedule.workflow))
            .where(
                and_(
                    WorkflowSchedule.status == ScheduleStatus.ACTIVE,
                    WorkflowSchedule.next_run_at <= cutoff,
                    WorkflowSchedule.next_run_at.isnot(None)
                )
            )
            .limit(MAX_SCHEDULES_PER_TICK)
            .order_by(WorkflowSchedule.next_run_at)
        )

        schedules = result.scalars().all()

        if not schedules:
            logger.debug("No schedules due")
            return {
                "status": "success",
                "processed": 0,
                "triggered": 0,
                "skipped": 0,
                "errors": 0
            }

        logger.info(f"Found {len(schedules)} due schedules")

        processed = 0
        triggered = 0
        skipped = 0
        errors = 0

        for schedule in schedules:
            try:
                success = await _trigger_scheduled_workflow(db, schedule)
                processed += 1

                if success:
                    triggered += 1
                else:
                    skipped += 1

            except Exception as e:
                logger.error(
                    f"Error processing schedule {schedule.id}: {e}",
                    extra={
                        "schedule_id": str(schedule.id),
                        "workflow_id": str(schedule.workflow_id),
                        "traceback": traceback.format_exc()
                    }
                )
                errors += 1

                # Record the error on the schedule
                schedule.error_count += 1
                schedule.consecutive_errors += 1

                if schedule.consecutive_errors >= schedule.max_consecutive_errors:
                    schedule.status = ScheduleStatus.PAUSED
                    logger.warning(
                        f"Schedule {schedule.id} auto-paused after {schedule.consecutive_errors} consecutive errors"
                    )

                # Still update next_run_at to prevent infinite retries
                schedule.update_next_run()

        await db.commit()

        logger.info(
            f"Scheduler tick complete: processed={processed}, triggered={triggered}, "
            f"skipped={skipped}, errors={errors}"
        )

        return {
            "status": "success",
            "processed": processed,
            "triggered": triggered,
            "skipped": skipped,
            "errors": errors,
            "timestamp": now.isoformat()
        }


async def _trigger_scheduled_workflow(
        db,
        schedule: WorkflowSchedule
) -> bool:
    """
    Triggers a workflow execution for a schedule.

    Args:
        db: Database session
        schedule: The schedule to trigger

    Returns:
        True if triggered successfully, False if skipped
    """
    # Validate workflow exists and is runnable
    workflow = schedule.workflow
    if not workflow:
        logger.warning(f"Schedule {schedule.id} has no associated workflow")
        return False

    if workflow.status != WorkflowStatus.PUBLISHED:
        logger.warning(
            f"Schedule {schedule.id} workflow not published (status: {workflow.status})",
            extra={"workflow_id": str(workflow.id)}
        )
        return False

    # Check if workflow has nodes
    if not workflow.graph_definition or not workflow.graph_definition.get("nodes"):
        logger.warning(f"Schedule {schedule.id} workflow has no nodes")
        return False

    # Create execution record
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = WorkflowExecution(
        id=execution_id,
        workflow_id=workflow.id,
        status=ExecutionStatus.PENDING,
        trigger_type="SCHEDULED",
        started_at=now,
        context_data={
            "schedule_metadata": {
                "schedule_id": str(schedule.id),
                "schedule_name": schedule.name,
                "scheduled_time": schedule.next_run_at.isoformat() if schedule.next_run_at else now.isoformat(),
                "run_number": schedule.run_count + 1
            }
        }
    )

    db.add(execution)
    await db.flush()

    # Prepare input data for workflow
    initial_input = {
        # Schedule metadata (passed to ScheduleTriggerNode)
        "schedule_id": str(schedule.id),
        "schedule_type": schedule.schedule_type.value.lower(),
        "scheduled_time": schedule.next_run_at.isoformat() if schedule.next_run_at else now.isoformat(),
        "run_number": schedule.run_count + 1,
        "trigger_type": "scheduled",

        # User-defined input data
        "input_data": schedule.input_data or {},

        # Merge user input into top level for convenience
        **schedule.input_data
    }

    # Queue the workflow execution using active dual-mode runtime queue
    from src.core.runtime import get_runtime
    runtime = get_runtime()
    if runtime and runtime.queue:
        runtime.queue.enqueue(
            "execute_workflow_task",
            str(execution_id),
            str(workflow.id),
            initial_input,
            None  # resume_node_id
        )
    else:
        logger.error("No active runtime found to queue workflow execution from schedule")

    # Update schedule record
    schedule.record_execution(execution_id, success=True)

    logger.info(
        f"Triggered scheduled workflow",
        extra={
            "schedule_id": str(schedule.id),
            "schedule_name": schedule.name,
            "workflow_id": str(workflow.id),
            "execution_id": str(execution_id),
            "run_number": schedule.run_count
        }
    )

    return True


# ============================================================
# SCHEDULE MANAGEMENT TASKS (CELERY-FREE)
# ============================================================

def create_schedule_from_workflow_task(
        workflow_id: str,
        user_id: str
) -> Dict[str, Any]:
    """
    Creates a schedule from a workflow's schedule trigger node configuration.

    Called when a workflow with a ScheduleTriggerNode is published.

    Args:
        workflow_id: Workflow UUID string
        user_id: User UUID string

    Returns:
        Created schedule info
    """
    return asyncio.run(_create_schedule_from_workflow_async(workflow_id, user_id))


async def _create_schedule_from_workflow_async(
        workflow_id: str,
        user_id: str
) -> Dict[str, Any]:
    """
    Async implementation of schedule creation from workflow.
    """
    from src.services.workflow_engine.nodes.trigger_schedule import (
        ScheduleTriggerNode,
        CRON_PRESETS,
        INTERVAL_PRESETS
    )

    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        # Load workflow
        workflow = await db.get(Workflow, UUID(workflow_id))
        if not workflow:
            return {"status": "error", "message": "Workflow not found"}

        # Find schedule trigger node
        nodes = workflow.graph_definition.get("nodes", [])
        schedule_node = None

        for node in nodes:
            if node.get("type") == "scheduleTriggerNode":
                schedule_node = node
                break

        if not schedule_node:
            return {"status": "skipped", "message": "No schedule trigger node found"}

        # Extract configuration
        config = schedule_node.get("data", {})
        schedule_type_str = config.get("schedule_type", "cron")
        enabled = config.get("enabled", True)

        if not enabled:
            return {"status": "skipped", "message": "Schedule is disabled in node config"}

        # Map to ScheduleType enum
        schedule_type_map = {
            "cron": ScheduleType.CRON,
            "interval": ScheduleType.INTERVAL,
            "once": ScheduleType.ONCE
        }
        schedule_type = schedule_type_map.get(schedule_type_str, ScheduleType.CRON)

        # Resolve cron expression
        cron_expression = None
        if schedule_type == ScheduleType.CRON:
            cron_preset = config.get("cron_preset", "custom")
            if cron_preset != "custom" and cron_preset in CRON_PRESETS:
                cron_expression = CRON_PRESETS[cron_preset]["cron"]
            else:
                cron_expression = config.get("cron_expression")

        # Resolve interval
        interval_seconds = None
        if schedule_type == ScheduleType.INTERVAL:
            interval_preset = config.get("interval_preset", "custom")
            if interval_preset != "custom" and interval_preset in INTERVAL_PRESETS:
                interval_seconds = INTERVAL_PRESETS[interval_preset]["seconds"]
            else:
                interval_seconds = config.get("interval_seconds")
                if interval_seconds:
                    interval_seconds = max(MIN_INTERVAL_SECONDS, int(interval_seconds))

        # Get run_at for one-time schedules
        run_at = None
        if schedule_type == ScheduleType.ONCE:
            run_at_str = config.get("run_at")
            if run_at_str:
                run_at = datetime.fromisoformat(run_at_str.replace("Z", "+00:00"))

        # Check for existing schedule
        existing = await db.execute(
            select(WorkflowSchedule).where(
                and_(
                    WorkflowSchedule.workflow_id == UUID(workflow_id),
                    WorkflowSchedule.status.in_([ScheduleStatus.ACTIVE, ScheduleStatus.PAUSED])
                )
            )
        )
        existing_schedule = existing.scalars().first()

        if existing_schedule:
            # Update existing schedule
            existing_schedule.schedule_type = schedule_type
            existing_schedule.cron_expression = cron_expression
            existing_schedule.interval_seconds = interval_seconds
            existing_schedule.run_at = run_at
            existing_schedule.timezone = config.get("timezone", "UTC")
            existing_schedule.status = ScheduleStatus.ACTIVE
            existing_schedule.update_next_run()

            await db.commit()

            return {
                "status": "updated",
                "schedule_id": str(existing_schedule.id),
                "next_run_at": existing_schedule.next_run_at.isoformat() if existing_schedule.next_run_at else None
            }

        # Create new schedule
        schedule = WorkflowSchedule(
            user_id=UUID(user_id),
            workflow_id=UUID(workflow_id),
            name=f"{workflow.name} Schedule",
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_at=run_at,
            timezone=config.get("timezone", "UTC"),
            status=ScheduleStatus.ACTIVE
        )

        # Calculate initial next_run_at
        schedule.update_next_run()

        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)

        logger.info(
            f"Created schedule for workflow",
            extra={
                "schedule_id": str(schedule.id),
                "workflow_id": workflow_id,
                "schedule_type": schedule_type.value,
                "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
            }
        )

        return {
            "status": "created",
            "schedule_id": str(schedule.id),
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
        }


def disable_workflow_schedules_task(
        workflow_id: str
) -> Dict[str, Any]:
    """
    Disables all schedules for a workflow.

    Called when a workflow is unpublished or deleted.

    Args:
        workflow_id: Workflow UUID string

    Returns:
        Result summary
    """
    return asyncio.run(_disable_workflow_schedules_async(workflow_id))


async def _disable_workflow_schedules_async(workflow_id: str) -> Dict[str, Any]:
    """Async implementation of schedule disabling."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        result = await db.execute(
            select(WorkflowSchedule).where(
                and_(
                    WorkflowSchedule.workflow_id == UUID(workflow_id),
                    WorkflowSchedule.status.in_([ScheduleStatus.ACTIVE, ScheduleStatus.PAUSED])
                )
            )
        )

        schedules = result.scalars().all()
        disabled_count = 0

        for schedule in schedules:
            schedule.disable()
            disabled_count += 1

        await db.commit()

        logger.info(f"Disabled {disabled_count} schedules for workflow {workflow_id}")

        return {
            "status": "success",
            "disabled_count": disabled_count
        }
