import asyncio
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from loguru import logger

from src.core.database import get_database_manager
from src.services.workflow_engine.executor import WorkflowExecutor
from src.dao.workflow_dao import WorkflowDAO
from src.models.sql.workflow.workflow import Workflow
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus, NodeExecutionTrace


from src.api.v1.routers.workflow.streams import emit_trace

# ============================================================
# PURE WORKFLOW LOGIC (CELERY-FREE)
# ============================================================

async def execute_workflow_logic(
        execution_id: str,
        workflow_id: str,
        initial_input: Dict[str, Any],
        resume_node_id: Optional[str] = None,
        single_node_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async workflow execution implementation.

    Args:
        execution_id: Execution UUID string
        workflow_id: Workflow UUID string
        initial_input: Initial input data
        resume_node_id: Optional resume point
        task: Celery task instance

    Returns:
        Execution result
    """
    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        try:
            # 1. Load workflow
            dao = WorkflowDAO(db)
            workflow = await dao.get_by_id(UUID(workflow_id))

            if not workflow:
                raise ValueError(f"Workflow {workflow_id} not found")

            # 2. Validate workflow can run
            if not workflow.graph_definition:
                raise ValueError("Workflow has no graph definition")

            nodes = workflow.graph_definition.get("nodes", [])
            if not nodes:
                raise ValueError("Workflow has no nodes")

            # 3. Get global variables
            global_vars = workflow.global_variables or {}

            # 4. Create executor
            executor = WorkflowExecutor(
                graph_definition=workflow.graph_definition,
                global_vars=global_vars
            )

            # 5. Execute workflow
            logger.info(f"Executing workflow {workflow_id}")

            async def trace_cb(data: Dict[str, Any]) -> None:
                await emit_trace(execution_id, data)

            result = await executor.run(
                execution_id=UUID(execution_id),
                initial_input=initial_input,
                db=db,
                user_id=workflow.user_id,
                workflow_id=UUID(workflow_id),
                resume_node_id=resume_node_id,
                trace_callback=trace_cb,
                single_node_id=single_node_id
            )

            # Update execution record with success status and results
            execution = await db.get(WorkflowExecution, UUID(execution_id))
            if execution:
                execution.status = ExecutionStatus.COMPLETED
                execution.finished_at = datetime.now(timezone.utc)
                execution.results = result
                execution.context_data = result

                # Save execution traces
                for trace_data in executor.get_traces():
                    trace = NodeExecutionTrace(
                        execution_id=UUID(execution_id),
                        node_id=trace_data["node_id"],
                        node_type=trace_data["node_type"],
                        status=trace_data["status"],
                        inputs=trace_data.get("inputs", {}),
                        outputs=trace_data.get("outputs", {}),
                        error_message=trace_data.get("error_message"),
                        duration_ms=trace_data.get("duration_ms", 0),
                        attempt_number=trace_data.get("attempt_number", 1)
                    )
                    db.add(trace)

                await db.commit()

                # Emit workflow_end trace to notify frontend
                await emit_trace(execution_id, {
                    "type": "workflow_end",
                    "status": "completed",
                    "execution_id": execution_id
                })

            logger.info(
                f"Execution {execution_id} completed",
                extra={
                    "execution_id": execution_id,
                    "result_keys": list(result.keys()) if result else []
                }
            )

            return {
                "status": "completed",
                "execution_id": execution_id,
                "result": result
            }

        except Exception as e:
            logger.error(
                "Workflow execution error: {}",
                str(e),
                extra={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "traceback": traceback.format_exc()
                }
            )
            try:
                await emit_trace(execution_id, {
                    "type": "workflow_end",
                    "status": "failed",
                    "execution_id": execution_id,
                    "error": str(e)
                })
            except Exception:
                pass
            raise


async def _mark_execution_failed(
        execution_id: str,
        error_message: str
) -> None:
    """Marks an execution as failed in the database."""
    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        try:
            execution = await db.get(WorkflowExecution, UUID(execution_id))

            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.finished_at = datetime.now(timezone.utc)

                if not execution.context_data:
                    execution.context_data = {}
                execution.context_data["error"] = error_message

                await db.commit()

                # Emit workflow_end trace to notify frontend
                try:
                    await emit_trace(execution_id, {
                        "type": "workflow_end",
                        "status": "failed",
                        "execution_id": execution_id,
                        "error": error_message
                    })
                except Exception:
                    pass

                logger.info(f"Marked execution {execution_id} as FAILED")

        except Exception as e:
            logger.error(f"Failed to update execution status: {e}")


# ============================================================
# UTILITY OPERATIONS (CELERY-FREE)
# ============================================================

async def cancel_execution_logic(
        execution_id: str,
        reason: str = "Cancelled by user"
) -> Dict[str, Any]:
    """
    Cancels a running execution.

    Args:
        execution_id: Execution UUID string
        reason: Cancellation reason

    Returns:
        Cancellation result
    """
    logger.info(f"Cancelling execution {execution_id}: {reason}")

    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        execution = await db.get(WorkflowExecution, UUID(execution_id))

        if not execution:
            return {"status": "error", "message": "Execution not found"}

        if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]:
            return {
                "status": "error",
                "message": f"Cannot cancel {execution.status.value} execution"
            }

        execution.status = ExecutionStatus.FAILED
        execution.finished_at = datetime.now(timezone.utc)

        if not execution.context_data:
            execution.context_data = {}
        execution.context_data["error"] = reason
        execution.context_data["cancelled"] = True

        await db.commit()

        return {"status": "cancelled", "execution_id": execution_id}


async def cleanup_stale_executions_logic(
        max_age_hours: int = 24
) -> Dict[str, Any]:
    """
    Cleans up stale executions that are stuck in RUNNING/PENDING state.

    Args:
        max_age_hours: Maximum age for running executions

    Returns:
        Cleanup result
    """
    from datetime import timedelta
    from sqlalchemy import update, and_

    logger.info(f"Cleaning up stale executions older than {max_age_hours} hours")

    db_manager = get_database_manager()
    async with db_manager.get_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        stmt = (
            update(WorkflowExecution)
            .where(
                and_(
                    WorkflowExecution.status.in_([
                        ExecutionStatus.RUNNING,
                        ExecutionStatus.PENDING
                    ]),
                    WorkflowExecution.started_at < cutoff
                )
            )
            .values(
                status=ExecutionStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                context_data={"error": "Execution timed out (cleanup task)"}
            )
        )

        result = await db.execute(stmt)
        await db.commit()

        count = result.rowcount
        logger.info(f"Cleaned up {count} stale executions")

        return {"status": "success", "cleaned_count": count}


# ============================================================
# SCHEDULED OPERATIONS (CELERY-FREE)
# ============================================================

def health_check_logic(worker_name: str = "unknown") -> Dict[str, Any]:
    """
    Worker health check logic.

    Returns:
        Health check result
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "worker": worker_name
    }