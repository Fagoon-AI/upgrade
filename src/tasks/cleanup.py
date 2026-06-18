import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text, delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.core.database import SessionLocal


# CLEANUP CONFIGURATION

class CleanupTarget(str, Enum):
    """Cleanup target types."""
    TRACES = "traces"
    EXECUTIONS = "executions"
    MEMORIES = "memories"
    DOCUMENTS = "documents"
    ALL = "all"


@dataclass
class CleanupConfig:
    """Configuration for cleanup operations."""
    batch_size: int = 1000          # Records per batch
    batch_delay_ms: int = 100       # Delay between batches (prevent CPU spike)
    max_batches: int = 1000         # Safety limit on total batches
    retention_days: int = 30        # Default retention period
    vacuum_after: bool = False      # Run VACUUM after cleanup (careful with this)


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    target: str
    total_deleted: int
    batches_processed: int
    duration_seconds: float
    cutoff_date: datetime
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "total_deleted": self.total_deleted,
            "batches_processed": self.batches_processed,
            "duration_seconds": round(self.duration_seconds, 2),
            "cutoff_date": self.cutoff_date.isoformat(),
            "errors": self.errors,
            "success": len(self.errors) == 0
        }


# ============================================================
# BATCH DELETION ENGINE
# ============================================================

class BatchDeleter:
    """
    Batch Deletion Engine.

    Features:
    - Configurable batch sizes
    - Progress tracking
    - Delay between batches to prevent resource exhaustion
    - Safe resumable operations
    """

    def __init__(self, config: CleanupConfig):
        self.config = config

    async def delete_in_batches(
            self,
            db: AsyncSession,
            table_name: str,
            date_column: str,
            cutoff_date: datetime,
            additional_conditions: Optional[str] = None
    ) -> CleanupResult:
        """
        Deletes records in batches to prevent table locks.

        Args:
            db: Database session
            table_name: Name of the table to clean
            date_column: Name of the date column to filter on
            cutoff_date: Delete records older than this
            additional_conditions: Optional SQL conditions

        Returns:
            CleanupResult with statistics
        """
        start_time = datetime.now(timezone.utc)
        total_deleted = 0
        batches_processed = 0
        errors = []

        try:
            # First, count how many records will be deleted
            count_query = text(f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE {date_column} < :cutoff_date
                {f'AND {additional_conditions}' if additional_conditions else ''}
            """)

            result = await db.execute(count_query, {"cutoff_date": cutoff_date})
            total_to_delete = result.scalar() or 0

            logger.info(f"Cleanup: Found {total_to_delete} records to delete from {table_name}")

            if total_to_delete == 0:
                return CleanupResult(
                    target=table_name,
                    total_deleted=0,
                    batches_processed=0,
                    duration_seconds=0,
                    cutoff_date=cutoff_date,
                    errors=[]
                )

            # Delete in batches
            while batches_processed < self.config.max_batches:
                # Use subquery to select IDs to delete (most efficient approach)
                # This prevents long-running transactions
                delete_query = text(f"""
                    DELETE FROM {table_name}
                    WHERE id IN (
                        SELECT id FROM {table_name}
                        WHERE {date_column} < :cutoff_date
                        {f'AND {additional_conditions}' if additional_conditions else ''}
                        LIMIT :batch_size
                    )
                """)

                try:
                    result = await db.execute(delete_query, {
                        "cutoff_date": cutoff_date,
                        "batch_size": self.config.batch_size
                    })

                    deleted_count = result.rowcount
                    await db.commit()

                    total_deleted += deleted_count
                    batches_processed += 1

                    logger.debug(
                        f"Cleanup batch {batches_processed}: "
                        f"Deleted {deleted_count} from {table_name} "
                        f"(total: {total_deleted}/{total_to_delete})"
                    )

                    # Exit if no more records to delete
                    if deleted_count == 0 or deleted_count < self.config.batch_size:
                        break

                    # Delay between batches to prevent resource exhaustion
                    if self.config.batch_delay_ms > 0:
                        await asyncio.sleep(self.config.batch_delay_ms / 1000)

                except Exception as batch_error:
                    await db.rollback()
                    error_msg = f"Batch {batches_processed} failed: {batch_error}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    # Continue with next batch
                    continue

        except Exception as e:
            errors.append(f"Cleanup failed: {e}")
            logger.error(f"Cleanup error for {table_name}: {e}")

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        return CleanupResult(
            target=table_name,
            total_deleted=total_deleted,
            batches_processed=batches_processed,
            duration_seconds=duration,
            cutoff_date=cutoff_date,
            errors=errors
        )


# ============================================================
# CLEANUP SERVICE
# ============================================================

class CleanupService:
    """
    Cleanup Service.

    Manages cleanup operations across all tables with:
    - Proper foreign key ordering
    - Batch deletion
    - Progress reporting
    - Error handling
    """

    def __init__(self, config: Optional[CleanupConfig] = None):
        self.config = config or CleanupConfig()
        self.deleter = BatchDeleter(self.config)

    async def cleanup_traces(
            self,
            db: AsyncSession,
            cutoff_date: datetime
    ) -> CleanupResult:
        """Cleans up node execution traces."""
        return await self.deleter.delete_in_batches(
            db=db,
            table_name="nodeexecutiontrace",
            date_column="created_at",
            cutoff_date=cutoff_date
        )

    async def cleanup_executions(
            self,
            db: AsyncSession,
            cutoff_date: datetime
    ) -> CleanupResult:
        """Cleans up workflow executions."""
        return await self.deleter.delete_in_batches(
            db=db,
            table_name="workflowexecution",
            date_column="started_at",
            cutoff_date=cutoff_date
        )

    async def cleanup_memories(
            self,
            db: AsyncSession,
            cutoff_date: datetime,
            workflow_id: Optional[str] = None
    ) -> CleanupResult:
        """Cleans up workflow memories."""
        additional = f"workflow_id = '{workflow_id}'" if workflow_id else None
        return await self.deleter.delete_in_batches(
            db=db,
            table_name="workflowmemory",
            date_column="created_at",
            cutoff_date=cutoff_date,
            additional_conditions=additional
        )

    async def cleanup_all(
            self,
            db: AsyncSession,
            retention_days: int = 30
    ) -> Dict[str, Any]:
        """
        Performs full cleanup across all tables.

        Order matters due to foreign key constraints:
        1. Node traces (references executions)
        2. Executions (references workflows)
        3. Memories (independent)
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        results = {}

        logger.info(f"Starting full cleanup (retention: {retention_days} days)")

        # 1. Traces first (FK dependency on executions)
        trace_result = await self.cleanup_traces(db, cutoff_date)
        results["traces"] = trace_result.to_dict()

        # 2. Executions
        exec_result = await self.cleanup_executions(db, cutoff_date)
        results["executions"] = exec_result.to_dict()

        # 3. Memories (optional, independent)
        memory_result = await self.cleanup_memories(db, cutoff_date)
        results["memories"] = memory_result.to_dict()

        # Summary
        total_deleted = (
                trace_result.total_deleted +
                exec_result.total_deleted +
                memory_result.total_deleted
        )

        total_errors = (
                trace_result.errors +
                exec_result.errors +
                memory_result.errors
        )

        results["summary"] = {
            "total_deleted": total_deleted,
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "success": len(total_errors) == 0,
            "errors": total_errors
        }

        logger.info(f"Full cleanup complete: {total_deleted} records deleted")

        return results

    async def get_cleanup_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Returns statistics about data eligible for cleanup.

        Useful for planning cleanup operations.
        """
        now = datetime.now(timezone.utc)

        stats = {}

        # Check each retention period
        for days in [7, 14, 30, 60, 90]:
            cutoff = now - timedelta(days=days)

            trace_count = await self._count_records(
                db, "nodeexecutiontrace", "created_at", cutoff
            )
            exec_count = await self._count_records(
                db, "workflowexecution", "started_at", cutoff
            )
            memory_count = await self._count_records(
                db, "workflowmemory", "created_at", cutoff
            )

            stats[f"{days}_days"] = {
                "traces": trace_count,
                "executions": exec_count,
                "memories": memory_count,
                "total": trace_count + exec_count + memory_count
            }

        return stats

    async def _count_records(
            self,
            db: AsyncSession,
            table_name: str,
            date_column: str,
            cutoff_date: datetime
    ) -> int:
        """Counts records older than cutoff date."""
        try:
            query = text(f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE {date_column} < :cutoff_date
            """)
            result = await db.execute(query, {"cutoff_date": cutoff_date})
            return result.scalar() or 0
        except Exception:
            return 0


# ============================================================
# CLEANUP TASKS (CELERY-FREE)
# ============================================================

def cleanup_old_logs_task(retention_days: int = 30, batch_size: int = 1000):
    """
    Entry point for periodic database housekeeping.
    """
    return asyncio.run(_run_cleanup(retention_days, batch_size))


def cleanup_traces_task(retention_days: int = 7, batch_size: int = 2000):
    """
    Dedicated task for trace cleanup (runs more frequently, larger batches).

    Traces are high-volume and can be cleaned more aggressively.
    """
    return asyncio.run(_run_trace_cleanup(retention_days, batch_size))


async def _run_cleanup(retention_days: int, batch_size: int) -> Dict[str, Any]:
    """Internal async cleanup runner."""
    config = CleanupConfig(
        batch_size=batch_size,
        retention_days=retention_days,
        batch_delay_ms=50  # Small delay between batches
    )

    service = CleanupService(config)

    async with SessionLocal() as db:
        try:
            results = await service.cleanup_all(db, retention_days)
            return results
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}")
            return {"error": str(e), "success": False}


async def _run_trace_cleanup(retention_days: int, batch_size: int) -> Dict[str, Any]:
    """Internal async trace cleanup runner."""
    config = CleanupConfig(
        batch_size=batch_size,
        batch_delay_ms=25  # Faster for traces
    )

    service = CleanupService(config)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with SessionLocal() as db:
        try:
            result = await service.cleanup_traces(db, cutoff_date)
            return result.to_dict()
        except Exception as e:
            logger.error(f"Trace cleanup failed: {e}")
            return {"error": str(e), "success": False}


# ============================================================
# STANDALONE CLEANUP FUNCTION
# ============================================================

async def purge_old_execution_data(
        retention_days: int = 30,
        batch_size: int = 1000
) -> Dict[str, Any]:
    """
    Standalone function for manual cleanup.

    Can be called directly without Celery:
        await purge_old_execution_data(retention_days=30)
    """
    config = CleanupConfig(
        batch_size=batch_size,
        retention_days=retention_days
    )

    service = CleanupService(config)

    async with SessionLocal() as db:
        return await service.cleanup_all(db, retention_days)