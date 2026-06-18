from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.exc import IntegrityError
from loguru import logger

from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.execution import WorkflowExecution


class WorkflowDAOError(Exception):
    """Base exception for DAO operations."""
    pass


class WorkflowNotFoundError(WorkflowDAOError):
    """Raised when workflow is not found."""
    pass


class ConcurrentUpdateError(WorkflowDAOError):
    """Raised when concurrent update is detected."""
    pass


class WorkflowDAO:
    """
    Data Access Object for Workflows.

    Features:
    - CRUD operations with validation
    - Optimistic locking via version field
    - Efficient eager loading
    - Search and filtering
    - Batch operations
    - Soft delete support
    - Audit trail ready
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============================================================
    # CREATE
    # ============================================================

    async def create(self, workflow: Workflow) -> Workflow:
        """
        Creates a new workflow.

        Args:
            workflow: Workflow instance to create

        Returns:
            Created workflow with ID

        Raises:
            IntegrityError: If workflow with same name exists for user
        """
        try:
            self.db.add(workflow)
            await self.db.commit()
            await self.db.refresh(workflow)

            logger.info(
                f"Workflow created: {workflow.id}",
                extra={"user_id": str(workflow.user_id)}
            )

            return workflow

        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Failed to create workflow: {e}")
            raise

    async def create_with_version(
            self,
            workflow: Workflow,
            initial_graph: Dict[str, Any],
            description: str = "Initial version"
    ) -> Tuple[Workflow, WorkflowVersion]:
        """
        Creates workflow with initial version atomically.

        Args:
            workflow: Workflow instance
            initial_graph: Initial graph definition
            description: Version description

        Returns:
            Tuple of (workflow, version)
        """
        try:
            # Add workflow
            self.db.add(workflow)
            await self.db.flush()

            # Create initial version
            version = WorkflowVersion(
                workflow_id=workflow.id,
                version_number=1,
                graph_snapshot=initial_graph,
                description=description
            )
            self.db.add(version)
            await self.db.flush()

            # Link version to workflow
            workflow.active_version_id = version.id
            workflow.graph_definition = initial_graph

            await self.db.commit()
            await self.db.refresh(workflow)

            return workflow, version

        except Exception as e:
            await self.db.rollback()
            raise

    # ============================================================
    # READ
    # ============================================================

    async def get_by_id(
            self,
            workflow_id: UUID,
            include_versions: bool = True,
            include_executions: bool = False
    ) -> Optional[Workflow]:
        """
        Gets workflow by ID with optional eager loading.

        Args:
            workflow_id: Workflow UUID
            include_versions: Load versions relationship
            include_executions: Load executions relationship

        Returns:
            Workflow or None if not found
        """
        query = select(Workflow).where(Workflow.id == workflow_id)

        # Eager loading options
        if include_versions:
            query = query.options(selectinload(Workflow.versions))

        if include_executions:
            query = query.options(selectinload(Workflow.executions))

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_id_for_user(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> Optional[Workflow]:
        """
        Gets workflow by ID with user ownership check.

        Args:
            workflow_id: Workflow UUID
            user_id: Owner user UUID

        Returns:
            Workflow or None if not found or not owned
        """
        query = (
            select(Workflow)
            .where(
                and_(
                    Workflow.id == workflow_id,
                    Workflow.user_id == user_id
                )
            )
            .options(selectinload(Workflow.versions))
        )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_all_by_user(
            self,
            user_id: UUID,
            skip: int = 0,
            limit: int = 100,
            status_filter: Optional[WorkflowStatus] = None,
            search: Optional[str] = None,
            sort_by: str = "updated_at",
            sort_desc: bool = True
    ) -> List[Workflow]:
        """
        Gets all workflows for a user with filtering and pagination.

        Args:
            user_id: User UUID
            skip: Number of records to skip
            limit: Maximum records to return
            status_filter: Filter by status
            search: Search in name and description
            sort_by: Field to sort by
            sort_desc: Sort descending

        Returns:
            List of workflows
        """
        # Validate pagination
        skip = max(0, skip)
        limit = min(max(1, limit), 1000)

        # Build query
        query = select(Workflow).where(Workflow.user_id == user_id)

        # Apply status filter
        if status_filter:
            query = query.where(Workflow.status == status_filter)

        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Workflow.name.ilike(search_term),
                    Workflow.description.ilike(search_term)
                )
            )

        # Apply sorting
        sort_column = getattr(Workflow, sort_by, Workflow.updated_at)
        if sort_desc:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Eager load versions
        query = query.options(selectinload(Workflow.versions))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
            self,
            user_id: UUID,
            status_filter: Optional[WorkflowStatus] = None
    ) -> int:
        """
        Counts workflows for a user.

        Args:
            user_id: User UUID
            status_filter: Optional status filter

        Returns:
            Count of workflows
        """
        query = (
            select(func.count())
            .select_from(Workflow)
            .where(Workflow.user_id == user_id)
        )

        if status_filter:
            query = query.where(Workflow.status == status_filter)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def exists(self, workflow_id: UUID) -> bool:
        """Checks if workflow exists."""
        query = (
            select(func.count())
            .select_from(Workflow)
            .where(Workflow.id == workflow_id)
        )
        result = await self.db.execute(query)
        return (result.scalar() or 0) > 0

    # ============================================================
    # UPDATE
    # ============================================================

    async def update(self, workflow: Workflow) -> Workflow:
        """
        Updates a workflow.

        Args:
            workflow: Workflow with updated fields

        Returns:
            Updated workflow
        """
        workflow.updated_at = datetime.now(timezone.utc)

        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)

        return workflow

    async def update_with_version_check(
            self,
            workflow_id: UUID,
            expected_version: int,
            updates: Dict[str, Any]
    ) -> Workflow:
        """
        Updates workflow with optimistic locking.

        Args:
            workflow_id: Workflow UUID
            expected_version: Expected version number
            updates: Dictionary of fields to update

        Returns:
            Updated workflow

        Raises:
            ConcurrentUpdateError: If version doesn't match
            WorkflowNotFoundError: If workflow not found
        """
        # Get current workflow
        workflow = await self.get_by_id(workflow_id)

        if not workflow:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

        if workflow.version != expected_version:
            raise ConcurrentUpdateError(
                f"Workflow was modified by another process. "
                f"Expected version {expected_version}, found {workflow.version}"
            )

        # Apply updates
        for key, value in updates.items():
            if hasattr(workflow, key):
                setattr(workflow, key, value)

        # Increment version
        workflow.version += 1
        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)

        return workflow

    async def update_status(
            self,
            workflow_id: UUID,
            status: WorkflowStatus
    ) -> bool:
        """
        Updates workflow status.

        Args:
            workflow_id: Workflow UUID
            status: New status

        Returns:
            True if updated, False if not found
        """
        stmt = (
            update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(
                status=status,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount > 0

    # ============================================================
    # DELETE
    # ============================================================

    async def delete(self, workflow_id: UUID) -> bool:
        """
        Hard deletes a workflow.

        Args:
            workflow_id: Workflow UUID

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(Workflow).where(Workflow.id == workflow_id)
        result = await self.db.execute(stmt)
        await self.db.commit()

        if result.rowcount > 0:
            logger.info(f"Workflow deleted: {workflow_id}")
            return True

        return False

    async def soft_delete(self, workflow_id: UUID) -> bool:
        """
        Soft deletes a workflow by archiving it.

        Args:
            workflow_id: Workflow UUID

        Returns:
            True if archived, False if not found
        """
        return await self.update_status(workflow_id, WorkflowStatus.ARCHIVED)

    async def delete_by_user(self, user_id: UUID) -> int:
        """
        Deletes all workflows for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of deleted workflows
        """
        stmt = delete(Workflow).where(Workflow.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount

    # ============================================================
    # BATCH OPERATIONS
    # ============================================================

    async def get_batch(self, workflow_ids: List[UUID]) -> List[Workflow]:
        """
        Gets multiple workflows by IDs.

        Args:
            workflow_ids: List of workflow UUIDs

        Returns:
            List of found workflows
        """
        if not workflow_ids:
            return []

        query = (
            select(Workflow)
            .where(Workflow.id.in_(workflow_ids))
            .options(selectinload(Workflow.versions))
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_batch_status(
            self,
            workflow_ids: List[UUID],
            status: WorkflowStatus
    ) -> int:
        """
        Updates status for multiple workflows.

        Args:
            workflow_ids: List of workflow UUIDs
            status: New status

        Returns:
            Number of updated workflows
        """
        if not workflow_ids:
            return 0

        stmt = (
            update(Workflow)
            .where(Workflow.id.in_(workflow_ids))
            .values(
                status=status,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount

    # ============================================================
    # VERSION OPERATIONS
    # ============================================================

    async def get_versions(self, workflow_id: UUID) -> List[WorkflowVersion]:
        """
        Gets all versions for a workflow.

        Args:
            workflow_id: Workflow UUID

        Returns:
            List of versions ordered by version number descending
        """
        query = (
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version_number.desc())
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_version(
            self,
            workflow_id: UUID,
            version_number: int
    ) -> Optional[WorkflowVersion]:
        """
        Gets a specific version.

        Args:
            workflow_id: Workflow UUID
            version_number: Version number

        Returns:
            WorkflowVersion or None
        """
        query = (
            select(WorkflowVersion)
            .where(
                and_(
                    WorkflowVersion.workflow_id == workflow_id,
                    WorkflowVersion.version_number == version_number
                )
            )
        )

        result = await self.db.execute(query)
        return result.scalars().first()

    async def create_version(
            self,
            workflow_id: UUID,
            graph_snapshot: Dict[str, Any],
            description: Optional[str] = None
    ) -> WorkflowVersion:
        """
        Creates a new version for a workflow.

        Args:
            workflow_id: Workflow UUID
            graph_snapshot: Graph definition to snapshot
            description: Version description

        Returns:
            Created version
        """
        # Get current version count
        versions = await self.get_versions(workflow_id)
        next_version = len(versions) + 1

        version = WorkflowVersion(
            workflow_id=workflow_id,
            version_number=next_version,
            graph_snapshot=graph_snapshot,
            description=description or f"Version {next_version}"
        )

        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)

        return version

    # ============================================================
    # EXECUTION QUERIES
    # ============================================================

    async def get_recent_executions(
            self,
            workflow_id: UUID,
            limit: int = 10
    ) -> List[WorkflowExecution]:
        """
        Gets recent executions for a workflow.

        Args:
            workflow_id: Workflow UUID
            limit: Maximum executions to return

        Returns:
            List of recent executions
        """
        query = (
            select(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
            .order_by(WorkflowExecution.started_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_executions(
            self,
            workflow_id: UUID,
            status: Optional[str] = None
    ) -> int:
        """
        Counts executions for a workflow.

        Args:
            workflow_id: Workflow UUID
            status: Optional status filter

        Returns:
            Execution count
        """
        query = (
            select(func.count())
            .select_from(WorkflowExecution)
            .where(WorkflowExecution.workflow_id == workflow_id)
        )

        if status:
            query = query.where(WorkflowExecution.status == status)

        result = await self.db.execute(query)
        return result.scalar() or 0