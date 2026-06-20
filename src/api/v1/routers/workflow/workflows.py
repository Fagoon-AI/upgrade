from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus
from src.models.sql.workflow.version import WorkflowVersion
from src.schemas.workflow.response import APIResponse
from src.schemas.workflow.workflow import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowGraph
)
from src.schemas.workflow.execution import ExecutionResponse
from src.dao.workflow_dao import WorkflowDAO
from src.services.workflow.workflow_service import WorkflowService
from src.services.workflow.graph_validation import GraphValidationService


router = APIRouter()


# ============================================================
# DEPENDENCIES
# ============================================================

def get_workflow_service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    """Creates WorkflowService with dependencies."""
    return WorkflowService(workflow_dao=WorkflowDAO(db), db_session=db)


async def get_workflow_or_404(
        workflow_id: UUID,
        current_user: User,
        db: AsyncSession
) -> Workflow:
    """Gets workflow or raises 404."""
    query = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.versions))
    )
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

@router.post(
    "",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow",
    description="Create a new workflow"
)
async def create_workflow(
        request: Request,
        workflow_in: WorkflowCreate,
        current_user: User = Depends(get_current_user),
        service: WorkflowService = Depends(get_workflow_service)
):
    """Creates a new workflow."""
    workflow = await service.create_workflow(
        user_id=current_user.id,
        workflow_in=workflow_in
    )

    logger.info(
        f"Workflow created: {workflow.id}",
        extra={"user_id": str(current_user.id), "workflow_id": str(workflow.id)}
    )

    return APIResponse(
        success=True,
        message="Workflow created successfully",
        data=WorkflowResponse.model_validate(workflow)
    )


@router.get(
    "",
    response_model=APIResponse[List[WorkflowResponse]],
    summary="List workflows",
    description="Get all workflows for current user with pagination and filtering"
)
async def list_workflows(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Maximum records to return"),
        status_filter: Optional[WorkflowStatus] = Query(None, alias="status", description="Filter by status"),
        search: Optional[str] = Query(None, description="Search in name and description"),
        sort_by: str = Query("updated_at", description="Sort field"),
        sort_order: str = Query("desc", description="Sort order: asc or desc"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Lists workflows with pagination and filtering."""
    # Build query
    query = select(Workflow).where(Workflow.user_id == current_user.id)

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
    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset(skip).limit(limit)
    query = query.options(selectinload(Workflow.versions))

    result = await db.execute(query)
    workflows = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {total} workflows",
        data=[WorkflowResponse.model_validate(w) for w in workflows],
        meta={
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + len(workflows) < total
        }
    )


@router.get(
    "/{workflow_id}",
    response_model=APIResponse[WorkflowResponse],
    summary="Get workflow",
    description="Get a specific workflow by ID"
)
async def get_workflow(
        workflow_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Gets a workflow by ID."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    return APIResponse(
        success=True,
        message="Workflow retrieved",
        data=WorkflowResponse.model_validate(workflow)
    )


@router.put(
    "/{workflow_id}",
    response_model=APIResponse[WorkflowResponse],
    summary="Update workflow",
    description="Update workflow metadata and/or graph"
)
async def update_workflow(
        workflow_id: UUID,
        workflow_in: WorkflowUpdate,
        current_user: User = Depends(get_current_user),
        service: WorkflowService = Depends(get_workflow_service)
):
    """Updates a workflow."""
    workflow = await service.update_workflow(
        user_id=current_user.id,
        workflow_id=workflow_id,
        workflow_update=workflow_in
    )

    logger.info(
        f"Workflow updated: {workflow.id}",
        extra={"user_id": str(current_user.id), "workflow_id": str(workflow.id)}
    )

    return APIResponse(
        success=True,
        message="Workflow updated successfully",
        data=WorkflowResponse.model_validate(workflow)
    )


@router.delete(
    "/{workflow_id}",
    response_model=APIResponse,
    summary="Delete workflow",
    description="Delete a workflow (soft delete by archiving)"
)
async def delete_workflow(
        workflow_id: UUID,
        hard_delete: bool = Query(False, description="Permanently delete (admin only)"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Deletes a workflow (soft delete)."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    if hard_delete:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hard delete requires admin privileges"
            )
        await db.delete(workflow)
    else:
        # Soft delete - archive
        workflow.status = WorkflowStatus.ARCHIVED
        workflow.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        f"Workflow {'deleted' if hard_delete else 'archived'}: {workflow_id}",
        extra={"user_id": str(current_user.id), "workflow_id": str(workflow_id)}
    )

    return APIResponse(
        success=True,
        message=f"Workflow {'deleted' if hard_delete else 'archived'} successfully"
    )


# ============================================================
# ADVANCED OPERATIONS
# ============================================================

@router.post(
    "/{workflow_id}/clone",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Clone workflow",
    description="Create a copy of an existing workflow"
)
async def clone_workflow(
        workflow_id: UUID,
        new_name: Optional[str] = Query(None, description="Name for cloned workflow"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Clones a workflow."""
    source = await get_workflow_or_404(workflow_id, current_user, db)

    # Create new workflow
    cloned = Workflow(
        name=new_name or f"{source.name} (Copy)",
        description=source.description,
        user_id=current_user.id,
        graph_definition=source.graph_definition.copy(),
        status=WorkflowStatus.DRAFT,
        global_variables=source.global_variables.copy() if source.global_variables else {}
    )

    db.add(cloned)
    await db.flush()

    # Create initial version
    version = WorkflowVersion(
        workflow_id=cloned.id,
        version_number=1,
        graph_snapshot=source.graph_definition.copy(),
        description=f"Cloned from {source.name}"
    )
    db.add(version)
    await db.flush()

    cloned.active_version_id = version.id
    await db.commit()
    await db.refresh(cloned)

    logger.info(
        f"Workflow cloned: {source.id} -> {cloned.id}",
        extra={"user_id": str(current_user.id)}
    )

    return APIResponse(
        success=True,
        message="Workflow cloned successfully",
        data=WorkflowResponse.model_validate(cloned)
    )


@router.post(
    "/{workflow_id}/validate",
    response_model=APIResponse,
    summary="Validate workflow",
    description="Validate workflow graph structure"
)
async def validate_workflow(
        workflow_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Validates workflow graph."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    result = GraphValidationService.validate_graph(workflow.graph_definition)

    return APIResponse(
        success=result["is_valid"],
        message="Validation complete",
        data={
            "is_valid": result["is_valid"],
            "errors": result.get("errors", [])
        }
    )


@router.post(
    "/{workflow_id}/publish",
    response_model=APIResponse[WorkflowResponse],
    summary="Publish workflow",
    description="Publish workflow (validates and changes status)"
)
async def publish_workflow(
        workflow_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Publishes a workflow."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    # Validate before publishing
    result = GraphValidationService.validate_graph(workflow.graph_definition)

    if not result["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Cannot publish invalid workflow",
                "errors": result.get("errors", [])
            }
        )

    workflow.status = WorkflowStatus.PUBLISHED
    workflow.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(workflow)

    return APIResponse(
        success=True,
        message="Workflow published successfully",
        data=WorkflowResponse.model_validate(workflow)
    )


# ============================================================
# VERSION MANAGEMENT
# ============================================================

@router.get(
    "/{workflow_id}/versions",
    response_model=APIResponse[List[dict]],
    summary="List versions",
    description="Get version history for a workflow"
)
async def list_workflow_versions(
        workflow_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Lists workflow versions."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    query = (
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
    )

    result = await db.execute(query)
    versions = result.scalars().all()

    version_data = [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "description": v.description,
            "created_at": v.created_at.isoformat(),
            "is_active": v.id == workflow.active_version_id
        }
        for v in versions
    ]

    return APIResponse(
        success=True,
        message=f"Found {len(versions)} versions",
        data=version_data
    )


@router.post(
    "/{workflow_id}/versions/{version_id}/restore",
    response_model=APIResponse[WorkflowResponse],
    summary="Restore version",
    description="Restore workflow to a previous version"
)
async def restore_workflow_version(
        workflow_id: UUID,
        version_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Restores workflow to a previous version."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    # Get the version
    version = await db.get(WorkflowVersion, version_id)

    if not version or version.workflow_id != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )

    # Create new version from old snapshot
    new_version_number = len(workflow.versions) + 1
    new_version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=new_version_number,
        graph_snapshot=version.graph_snapshot.copy(),
        description=f"Restored from v{version.version_number}"
    )
    db.add(new_version)
    await db.flush()

    # Update workflow
    workflow.graph_definition = version.graph_snapshot.copy()
    workflow.active_version_id = new_version.id
    workflow.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(workflow)

    return APIResponse(
        success=True,
        message=f"Restored to version {version.version_number}",
        data=WorkflowResponse.model_validate(workflow)
    )


# ============================================================
# EXECUTION HISTORY
# ============================================================

@router.get(
    "/{workflow_id}/executions",
    response_model=APIResponse[List[ExecutionResponse]],
    summary="List executions",
    description="Get execution history for a workflow"
)
async def list_workflow_executions(
        workflow_id: UUID,
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        status_filter: Optional[ExecutionStatus] = Query(None, alias="status"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Lists workflow executions."""
    # Verify access
    await get_workflow_or_404(workflow_id, current_user, db)

    # Build query
    query = (
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == workflow_id)
    )

    if status_filter:
        query = query.where(WorkflowExecution.status == status_filter)

    query = query.order_by(WorkflowExecution.started_at.desc())

    # Get total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
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
# EXPORT/IMPORT
# ============================================================

@router.get(
    "/{workflow_id}/export",
    response_model=APIResponse,
    summary="Export workflow",
    description="Export workflow as JSON"
)
async def export_workflow(
        workflow_id: UUID,
        include_versions: bool = Query(False, description="Include version history"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Exports workflow as JSON."""
    workflow = await get_workflow_or_404(workflow_id, current_user, db)

    export_data = {
        "name": workflow.name,
        "description": workflow.description,
        "graph_definition": workflow.graph_definition,
        "global_variables": workflow.global_variables,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": workflow.version
    }

    if include_versions:
        export_data["versions"] = [
            {
                "version_number": v.version_number,
                "graph_snapshot": v.graph_snapshot,
                "description": v.description,
                "created_at": v.created_at.isoformat()
            }
            for v in workflow.versions
        ]

    return APIResponse(
        success=True,
        message="Workflow exported",
        data=export_data
    )


@router.post(
    "/import",
    response_model=APIResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Import workflow",
    description="Import workflow from JSON"
)
async def import_workflow(
        import_data: dict,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Imports workflow from JSON."""
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
                "errors": validation.get("errors", [])
            }
        )

    # Create workflow
    workflow = Workflow(
        name=import_data.get("name", "Imported Workflow"),
        description=import_data.get("description"),
        user_id=current_user.id,
        graph_definition=import_data["graph_definition"],
        global_variables=import_data.get("global_variables", {}),
        status=WorkflowStatus.DRAFT
    )

    db.add(workflow)
    await db.flush()

    # Create version
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=1,
        graph_snapshot=import_data["graph_definition"],
        description="Imported workflow"
    )
    db.add(version)
    await db.flush()

    workflow.active_version_id = version.id
    await db.commit()
    await db.refresh(workflow)

    logger.info(
        f"Workflow imported: {workflow.id}",
        extra={"user_id": str(current_user.id)}
    )

    return APIResponse(
        success=True,
        message="Workflow imported successfully",
        data=WorkflowResponse.model_validate(workflow)
    )