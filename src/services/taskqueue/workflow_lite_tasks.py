"""Lite-mode wrappers for workflow background tasks.
These call the async logic functions directly via InlineTaskQueue."""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


async def execute_workflow_lite(execution_id: str, workflow_id: str, initial_input: dict = None):
    from src.tasks.workflow import execute_workflow_logic
    await execute_workflow_logic(execution_id, workflow_id, initial_input or {})


async def cancel_execution_lite(execution_id: str):
    from src.tasks.workflow import cancel_execution_logic
    await cancel_execution_logic(execution_id)


async def cleanup_stale_executions_lite():
    from src.tasks.workflow import cleanup_stale_executions_logic
    await cleanup_stale_executions_logic()


async def process_due_schedules_lite():
    from src.tasks.scheduler import _process_due_schedules_async
    await _process_due_schedules_async()


async def create_schedule_from_workflow_lite(workflow_id: str, schedule_config: dict):
    from src.tasks.scheduler import _create_schedule_from_workflow_async
    await _create_schedule_from_workflow_async(workflow_id, schedule_config)


async def disable_workflow_schedules_lite(workflow_id: str):
    from src.tasks.scheduler import _disable_workflow_schedules_async
    await _disable_workflow_schedules_async(workflow_id)


async def cleanup_old_logs_lite(retention_days: int = 30, batch_size: int = 1000):
    from src.tasks.cleanup import _run_cleanup
    await _run_cleanup(retention_days, batch_size)


async def cleanup_traces_lite(retention_days: int = 7, batch_size: int = 2000):
    from src.tasks.cleanup import _run_trace_cleanup
    await _run_trace_cleanup(retention_days, batch_size)
