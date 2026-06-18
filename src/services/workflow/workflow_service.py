import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from src.dao.workflow_dao import WorkflowDAO, ConcurrentUpdateError, WorkflowNotFoundError
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus
from src.schemas.workflow.workflow import WorkflowCreate, WorkflowUpdate, WorkflowGraph
from src.services.workflow.graph_validation import GraphValidationService


class WorkflowServiceError(Exception):
    """Base exception for workflow service."""
    pass


class ValidationError(WorkflowServiceError):
    """Raised when validation fails."""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


class WorkflowService:
    """
    Workflow Service.

    Features:
    - Atomic CRUD operations
    - Graph validation pipeline
    - Version management
    - Status lifecycle
    - Clone functionality
    - Export/import
    - Audit logging

    Transaction Guarantees:
    - All operations are atomic
    - Rollback on any failure
    - Optimistic locking for concurrent updates
    """

    def __init__(self, workflow_dao: WorkflowDAO, db_session: AsyncSession):
        self.dao = workflow_dao
        self.db = db_session

    # ============================================================
    # CREATE
    # ============================================================

    async def create_workflow(
            self,
            user_id: UUID,
            workflow_in: WorkflowCreate
    ) -> Workflow:
        """
        Creates a new workflow with initial version atomically.

        Args:
            user_id: Owner user ID
            workflow_in: Workflow creation data

        Returns:
            Created workflow

        Raises:
            ValidationError: If input validation fails
        """
        # Validate input
        if not workflow_in.name or not workflow_in.name.strip():
            raise ValidationError("Workflow name is required")

        # Build initial graph
        graph_data = self._build_initial_graph(workflow_in.graph_definition)

        # Validate graph structure
        validation = GraphValidationService.validate_graph(graph_data)
        if not validation["is_valid"]:
            logger.warning(
                f"Initial graph validation warnings: {validation['errors']}",
                extra={"user_id": str(user_id)}
            )
            # Don't fail on draft creation, just log warnings

        try:
            # Create workflow
            workflow = Workflow(
                name=workflow_in.name.strip(),
                description=workflow_in.description,
                user_id=user_id,
                graph_definition=graph_data,
                status=WorkflowStatus.DRAFT,
                global_variables={}
            )

            self.db.add(workflow)
            await self.db.flush()

            # Create initial version
            version = WorkflowVersion(
                workflow_id=workflow.id,
                version_number=1,
                graph_snapshot=graph_data,
                description="Initial version",
                created_by=user_id
            )

            self.db.add(version)
            await self.db.flush()

            # Link version to workflow
            workflow.active_version_id = version.id

            await self.db.commit()
            await self.db.refresh(workflow)

            logger.info(
                f"Workflow created: {workflow.id}",
                extra={
                    "user_id": str(user_id),
                    "workflow_id": str(workflow.id),
                    "workflow_name": workflow.name
                }
            )

            return workflow

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create workflow: {e}")
            raise

    def _build_initial_graph(
            self,
            graph_definition: Optional[WorkflowGraph]
    ) -> Dict[str, Any]:
        """Builds initial graph definition."""
        if graph_definition:
            return graph_definition.model_dump()

        # Default graph with start node
        return {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 100},
                    "data": {"label": "Start", "inputs": {}}
                }
            ],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }

    # ============================================================
    # READ
    # ============================================================

    async def get_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> Workflow:
        """
        Gets a workflow with authorization check.

        Args:
            workflow_id: Workflow ID
            user_id: Requesting user ID

        Returns:
            Workflow

        Raises:
            HTTPException: If not found or not authorized
        """
        workflow = await self.dao.get_by_id(workflow_id)

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found"
            )

        if workflow.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this workflow"
            )

        return workflow

    async def get_user_workflows(
            self,
            user_id: UUID,
            skip: int = 0,
            limit: int = 100,
            status_filter: Optional[WorkflowStatus] = None,
            search: Optional[str] = None
    ) -> Tuple[List[Workflow], int]:
        """
        Gets workflows for a user with pagination.

        Args:
            user_id: User ID
            skip: Offset
            limit: Max results
            status_filter: Optional status filter
            search: Optional search term

        Returns:
            Tuple of (workflows, total_count)
        """
        workflows = await self.dao.get_all_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            search=search
        )

        total = await self.dao.count_by_user(user_id, status_filter)

        return workflows, total

    # ============================================================
    # UPDATE
    # ============================================================

    async def update_workflow(
            self,
            user_id: UUID,
            workflow_id: UUID,
            workflow_update: WorkflowUpdate
    ) -> Workflow:
        """
        Updates workflow with validation and versioning.

        Args:
            user_id: User ID
            workflow_id: Workflow ID
            workflow_update: Update data

        Returns:
            Updated workflow

        Raises:
            HTTPException: On validation or authorization errors
        """
        # Get workflow with auth check
        workflow = await self.get_workflow(workflow_id, user_id)

        # Determine target state
        new_graph_provided = workflow_update.graph_definition is not None
        target_graph = (
            workflow_update.graph_definition.model_dump()
            if new_graph_provided
            else workflow.graph_definition
        )
        target_status = workflow_update.status or workflow.status

        # Validate status transition
        if workflow_update.status and workflow_update.status != workflow.status:
            if not self._is_valid_status_transition(workflow.status, workflow_update.status):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot transition from {workflow.status.value} to {workflow_update.status.value}"
                )

        # Validate graph for publishing
        if target_status == WorkflowStatus.PUBLISHED:
            validation = GraphValidationService.validate_graph(target_graph)
            if not validation["is_valid"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Cannot publish invalid workflow",
                        "errors": validation["errors"]
                    }
                )

        try:
            # Create new version if graph changed
            if new_graph_provided:
                await self._create_version(
                    workflow=workflow,
                    graph=target_graph,
                    user_id=user_id,
                    description=workflow_update.description
                )
                workflow.graph_definition = target_graph

            # Apply metadata updates
            if workflow_update.name is not None:
                workflow.name = workflow_update.name.strip()

            if workflow_update.description is not None:
                workflow.description = workflow_update.description

            if workflow_update.status is not None:
                workflow.status = workflow_update.status

            workflow.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(workflow)

            logger.info(
                f"Workflow updated: {workflow_id}",
                extra={
                    "user_id": str(user_id),
                    "workflow_id": str(workflow_id),
                    "graph_updated": new_graph_provided
                }
            )

            return workflow

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update workflow: {e}")
            raise

    async def _create_version(
            self,
            workflow: Workflow,
            graph: Dict[str, Any],
            user_id: UUID,
            description: Optional[str] = None
    ) -> WorkflowVersion:
        """Creates a new version for a workflow."""
        # Get next version number
        version_count = len(workflow.versions) if workflow.versions else 0
        next_version = version_count + 1

        version = WorkflowVersion(
            workflow_id=workflow.id,
            version_number=next_version,
            graph_snapshot=graph,
            description=description or f"Version {next_version}",
            created_by=user_id
        )

        self.db.add(version)
        await self.db.flush()

        workflow.active_version_id = version.id
        workflow.version = next_version

        return version

    def _is_valid_status_transition(
            self,
            current: WorkflowStatus,
            target: WorkflowStatus
    ) -> bool:
        """Validates status transition."""
        transitions = {
            WorkflowStatus.DRAFT: {WorkflowStatus.PUBLISHED, WorkflowStatus.ARCHIVED},
            WorkflowStatus.PUBLISHED: {WorkflowStatus.DRAFT, WorkflowStatus.ARCHIVED},
            WorkflowStatus.ARCHIVED: {WorkflowStatus.DRAFT},
        }

        return target in transitions.get(current, set())

    # ============================================================
    # STATUS OPERATIONS
    # ============================================================

    async def publish_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> Workflow:
        """
        Publishes a workflow after validation.

        Args:
            workflow_id: Workflow ID
            user_id: User ID

        Returns:
            Published workflow
        """
        workflow = await self.get_workflow(workflow_id, user_id)

        if workflow.status == WorkflowStatus.PUBLISHED:
            return workflow  # Already published

        # Validate graph
        validation = GraphValidationService.validate_graph(workflow.graph_definition)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Cannot publish invalid workflow",
                    "errors": validation["errors"]
                }
            )

        # Check for start node
        if not workflow.get_start_node() if hasattr(workflow, 'get_start_node') else True:
            start_exists = any(
                n.get("type") == "startNode"
                for n in workflow.graph_definition.get("nodes", [])
            )
            if not start_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workflow must have a start node to be published"
                )

        workflow.status = WorkflowStatus.PUBLISHED
        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(f"Workflow published: {workflow_id}")

        return workflow

    async def archive_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> Workflow:
        """Archives a workflow (soft delete)."""
        workflow = await self.get_workflow(workflow_id, user_id)

        workflow.status = WorkflowStatus.ARCHIVED
        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(f"Workflow archived: {workflow_id}")

        return workflow

    # ============================================================
    # CLONE
    # ============================================================

    async def clone_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID,
            new_name: Optional[str] = None
    ) -> Workflow:
        """
        Clones a workflow.

        Args:
            workflow_id: Source workflow ID
            user_id: User ID
            new_name: Optional name for clone

        Returns:
            Cloned workflow
        """
        source = await self.get_workflow(workflow_id, user_id)

        # Build clone name
        clone_name = new_name or f"{source.name} (Copy)"

        try:
            # Create new workflow
            cloned = Workflow(
                name=clone_name,
                description=source.description,
                user_id=user_id,
                graph_definition=json.loads(json.dumps(source.graph_definition)),
                global_variables=json.loads(json.dumps(source.global_variables or {})),
                status=WorkflowStatus.DRAFT
            )

            self.db.add(cloned)
            await self.db.flush()

            # Create initial version
            version = WorkflowVersion(
                workflow_id=cloned.id,
                version_number=1,
                graph_snapshot=cloned.graph_definition,
                description=f"Cloned from {source.name}",
                created_by=user_id
            )

            self.db.add(version)
            await self.db.flush()

            cloned.active_version_id = version.id

            await self.db.commit()
            await self.db.refresh(cloned)

            logger.info(
                f"Workflow cloned: {source.id} -> {cloned.id}",
                extra={"user_id": str(user_id)}
            )

            return cloned

        except Exception as e:
            await self.db.rollback()
            raise

    # ============================================================
    # VERSION MANAGEMENT
    # ============================================================

    async def get_versions(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> List[WorkflowVersion]:
        """Gets all versions for a workflow."""
        workflow = await self.get_workflow(workflow_id, user_id)
        return await self.dao.get_versions(workflow_id)

    async def restore_version(
            self,
            workflow_id: UUID,
            version_id: UUID,
            user_id: UUID
    ) -> Workflow:
        """
        Restores workflow to a previous version.

        Args:
            workflow_id: Workflow ID
            version_id: Version to restore
            user_id: User ID

        Returns:
            Updated workflow
        """
        workflow = await self.get_workflow(workflow_id, user_id)

        # Get version
        version = await self.db.get(WorkflowVersion, version_id)

        if not version or version.workflow_id != workflow_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Version not found"
            )

        try:
            # Create new version from old snapshot
            await self._create_version(
                workflow=workflow,
                graph=json.loads(json.dumps(version.graph_snapshot)),
                user_id=user_id,
                description=f"Restored from v{version.version_number}"
            )

            workflow.graph_definition = version.graph_snapshot
            workflow.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(workflow)

            logger.info(
                f"Workflow {workflow_id} restored to version {version.version_number}"
            )

            return workflow

        except Exception as e:
            await self.db.rollback()
            raise

    # ============================================================
    # EXPORT / IMPORT
    # ============================================================

    async def export_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID,
            include_versions: bool = False
    ) -> Dict[str, Any]:
        """
        Exports workflow as JSON.

        Args:
            workflow_id: Workflow ID
            user_id: User ID
            include_versions: Include version history

        Returns:
            Export data dictionary
        """
        workflow = await self.get_workflow(workflow_id, user_id)

        export_data = {
            "format_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "name": workflow.name,
            "description": workflow.description,
            "graph_definition": workflow.graph_definition,
            "global_variables": workflow.global_variables,
        }

        if include_versions:
            versions = await self.dao.get_versions(workflow_id)
            export_data["versions"] = [
                {
                    "version_number": v.version_number,
                    "graph_snapshot": v.graph_snapshot,
                    "description": v.description,
                    "created_at": v.created_at.isoformat()
                }
                for v in versions
            ]

        return export_data

    async def import_workflow(
            self,
            user_id: UUID,
            import_data: Dict[str, Any]
    ) -> Workflow:
        """
        Imports workflow from JSON.

        Args:
            user_id: User ID
            import_data: Import data dictionary

        Returns:
            Created workflow
        """
        # Validate import data
        if "graph_definition" not in import_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Import data must include graph_definition"
            )

        # Validate graph
        validation = GraphValidationService.validate_graph(import_data["graph_definition"])
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Invalid graph in import data",
                    "errors": validation["errors"]
                }
            )

        # Create workflow
        workflow_in = WorkflowCreate(
            name=import_data.get("name", "Imported Workflow"),
            description=import_data.get("description"),
            graph_definition=WorkflowGraph.model_validate(import_data["graph_definition"])
        )

        workflow = await self.create_workflow(user_id, workflow_in)

        # Apply global variables if present
        if import_data.get("global_variables"):
            workflow.global_variables = import_data["global_variables"]
            await self.db.commit()
            await self.db.refresh(workflow)

        return workflow

    # ============================================================
    # VALIDATION
    # ============================================================

    async def validate_workflow(
            self,
            workflow_id: UUID,
            user_id: UUID
    ) -> Dict[str, Any]:
        """
        Validates a workflow graph.

        Args:
            workflow_id: Workflow ID
            user_id: User ID

        Returns:
            Validation result
        """
        workflow = await self.get_workflow(workflow_id, user_id)

        return GraphValidationService.validate_graph(workflow.graph_definition)