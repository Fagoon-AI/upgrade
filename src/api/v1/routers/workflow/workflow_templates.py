"""
Workflow Templates API - Pre-built workflow templates for quick start.

Provides endpoints for browsing, viewing, and cloning workflow templates.
Templates are pre-configured workflows that users can clone to create
new workflows with predefined configurations.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict
from uuid import UUID
from collections import Counter

from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, String
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user, get_current_user_optional
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.template import WorkflowTemplate, TemplateCategory
from src.schemas.workflow.response import APIResponse
from src.schemas.workflow.template import (
    TemplateListResponse,
    TemplateDetailResponse,
    TemplateCloneRequest,
    TemplateCategoryInfo,
    TemplateStatsResponse,
    ClonedWorkflowResponse,
)


router = APIRouter()


# ============================================================
# CATEGORY DESCRIPTIONS
# ============================================================

CATEGORY_DESCRIPTIONS = {
    TemplateCategory.AI_AUTOMATION: "AI-powered automation workflows using LLMs and ML models",
    TemplateCategory.DATA_PROCESSING: "Data transformation, ETL, and processing pipelines",
    TemplateCategory.COMMUNICATION: "Email, messaging, and notification workflows",
    TemplateCategory.MARKETING: "Marketing automation and campaign workflows",
    TemplateCategory.CUSTOMER_SUPPORT: "Customer service and support automation",
    TemplateCategory.DEVELOPMENT: "Developer tools and CI/CD workflows",
    TemplateCategory.PRODUCTIVITY: "Personal and team productivity workflows",
    TemplateCategory.ANALYTICS: "Data analytics and reporting workflows",
    TemplateCategory.STARTER: "Simple starter templates for learning",
}


# ============================================================
# DEPENDENCIES
# ============================================================

async def get_template_or_404(
        template_id: UUID,
        db: AsyncSession,
        require_public: bool = True
) -> WorkflowTemplate:
    """
    Gets template by ID.

    Args:
        template_id: Template UUID
        db: Database session
        require_public: If True, only return public templates

    Returns:
        WorkflowTemplate if found

    Raises:
        HTTPException: 404 if not found or not accessible
    """
    query = select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)

    if require_public:
        query = query.where(WorkflowTemplate.is_public == True)

    result = await db.execute(query)
    template = result.scalars().first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return template


# ============================================================
# LIST ENDPOINTS
# ============================================================

@router.get(
    "",
    response_model=APIResponse[List[TemplateListResponse]],
    summary="List templates",
    description="Get all available workflow templates with filtering"
)
async def list_templates(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=100, description="Maximum records to return"),
        category: Optional[TemplateCategory] = Query(
            None,
            description="Filter by category"
        ),
        difficulty: Optional[str] = Query(
            None,
            description="Filter by difficulty (beginner, intermediate, advanced)"
        ),
        is_featured: Optional[bool] = Query(
            None,
            description="Filter for featured templates only"
        ),
        search: Optional[str] = Query(
            None,
            description="Search in name, description, and tags"
        ),
        tags: Optional[str] = Query(
            None,
            description="Comma-separated tags to filter by"
        ),
        required_connection: Optional[str] = Query(
            None,
            description="Filter by required connection provider"
        ),
        sort_by: str = Query(
            "clone_count",
            description="Sort field (name, clone_count, created_at, is_featured)"
        ),
        sort_order: str = Query(
            "desc",
            description="Sort order: asc or desc"
        ),
        current_user: Optional[User] = Depends(get_current_user_optional),
        db: AsyncSession = Depends(get_db)
):
    """
    Lists all available workflow templates.

    Templates are pre-built workflows that can be cloned to create
    new workflows. This endpoint returns public templates and
    optionally the user's own templates.

    Supports filtering by:
    - category: Template category
    - difficulty: beginner, intermediate, advanced
    - is_featured: Featured templates only
    - search: Search in name, description, tags
    - tags: Filter by specific tags
    - required_connection: Filter by required integrations

    Default sort is by popularity (clone_count descending).
    """
    # Build base query - only public templates
    query = select(WorkflowTemplate).where(
        WorkflowTemplate.is_public == True
    )

    # Apply filters
    if category:
        query = query.where(WorkflowTemplate.category == category)

    if difficulty:
        query = query.where(WorkflowTemplate.difficulty == difficulty)

    if is_featured is not None:
        query = query.where(WorkflowTemplate.is_featured == is_featured)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                WorkflowTemplate.name.ilike(search_term),
                WorkflowTemplate.description.ilike(search_term),
                WorkflowTemplate.short_description.ilike(search_term)
            )
        )

    if tags:
        # Filter templates that have any of the specified tags
        tag_list = [t.strip().lower() for t in tags.split(",")]
        # Using JSON contains for PostgreSQL
        # For each tag, check if it's in the tags array
        tag_conditions = []
        for tag in tag_list:
            tag_conditions.append(
                func.lower(func.cast(WorkflowTemplate.tags, String)).contains(tag.lower())
            )
        if tag_conditions:
            query = query.where(or_(*tag_conditions))

    if required_connection:
        # Filter templates that require a specific connection
        query = query.where(
            func.cast(WorkflowTemplate.required_connections, String).contains(required_connection.upper())
        )

    # Apply sorting
    sort_column_map = {
        "name": WorkflowTemplate.name,
        "clone_count": WorkflowTemplate.clone_count,
        "created_at": WorkflowTemplate.created_at,
        "is_featured": WorkflowTemplate.is_featured,
        "difficulty": WorkflowTemplate.difficulty,
    }
    sort_column = sort_column_map.get(sort_by, WorkflowTemplate.clone_count)

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

    result = await db.execute(query)
    templates = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {total} templates",
        data=[TemplateListResponse.from_template(t) for t in templates],
        meta={
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + len(templates) < total
        }
    )


@router.get(
    "/featured",
    response_model=APIResponse[List[TemplateListResponse]],
    summary="Get featured templates",
    description="Get featured templates for the homepage"
)
async def get_featured_templates(
        limit: int = Query(10, ge=1, le=50, description="Maximum templates to return"),
        db: AsyncSession = Depends(get_db)
):
    """
    Gets featured templates for homepage display.

    Returns the most popular featured templates, sorted by clone count.
    """
    query = (
        select(WorkflowTemplate)
        .where(
            and_(
                WorkflowTemplate.is_public == True,
                WorkflowTemplate.is_featured == True
            )
        )
        .order_by(WorkflowTemplate.clone_count.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    templates = result.scalars().all()

    return APIResponse(
        success=True,
        message=f"Found {len(templates)} featured templates",
        data=[TemplateListResponse.from_template(t) for t in templates]
    )


@router.get(
    "/categories",
    response_model=APIResponse[List[TemplateCategoryInfo]],
    summary="Get template categories",
    description="Get all categories with template counts"
)
async def get_categories(
        db: AsyncSession = Depends(get_db)
):
    """
    Gets all template categories with counts.

    Returns category information including description and
    number of templates in each category.
    """
    # Get counts per category
    query = (
        select(
            WorkflowTemplate.category,
            func.count(WorkflowTemplate.id).label("count")
        )
        .where(WorkflowTemplate.is_public == True)
        .group_by(WorkflowTemplate.category)
    )

    result = await db.execute(query)
    category_counts = {row[0]: row[1] for row in result.all()}

    # Build response with all categories
    categories = []
    for cat in TemplateCategory:
        categories.append(TemplateCategoryInfo(
            category=cat,
            count=category_counts.get(cat, 0),
            description=CATEGORY_DESCRIPTIONS.get(cat, "")
        ))

    # Sort by count descending
    categories.sort(key=lambda x: x.count, reverse=True)

    return APIResponse(
        success=True,
        message=f"Found {len(categories)} categories",
        data=categories
    )


# ============================================================
# DETAIL ENDPOINTS
# ============================================================

@router.get(
    "/{template_id}",
    response_model=APIResponse[TemplateDetailResponse],
    summary="Get template details",
    description="Get full details of a specific template"
)
async def get_template(
        template_id: UUID,
        db: AsyncSession = Depends(get_db)
):
    """
    Gets full details of a template including its graph definition.

    Returns the complete template configuration needed to
    understand what the template does and preview it.
    """
    template = await get_template_or_404(template_id, db)

    return APIResponse(
        success=True,
        message="Template retrieved",
        data=TemplateDetailResponse.from_template(template)
    )


@router.get(
    "/{template_id}/preview",
    response_model=APIResponse[Dict],
    summary="Preview template",
    description="Get template preview data for UI rendering"
)
async def preview_template(
        template_id: UUID,
        db: AsyncSession = Depends(get_db)
):
    """
    Gets preview data for rendering template in the UI.

    Returns the graph definition with node positions and
    connections for visual preview without cloning.
    """
    template = await get_template_or_404(template_id, db)

    graph = template.graph_definition or {"nodes": [], "edges": []}

    return APIResponse(
        success=True,
        message="Template preview",
        data={
            "template_id": str(template.id),
            "name": template.name,
            "description": template.description,
            "graph": graph,
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
            "required_connections": template.required_connections or [],
            "estimated_setup_minutes": template.estimated_setup_minutes
        }
    )


# ============================================================
# CLONE ENDPOINT
# ============================================================

@router.post(
    "/{template_id}/clone",
    response_model=APIResponse[ClonedWorkflowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Clone template to workflow",
    description="Create a new workflow from a template"
)
async def clone_template(
        template_id: UUID,
        clone_request: Optional[TemplateCloneRequest] = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Clones a template to create a new workflow.

    Creates a new workflow owned by the current user with the
    template's graph definition as its starting point.

    The workflow is created in DRAFT status and can be customized
    before publishing.

    Args:
        template_id: Template to clone
        clone_request: Optional name/description overrides

    Returns:
        The newly created workflow
    """
    template = await get_template_or_404(template_id, db)

    # Determine workflow name and description
    workflow_name = template.name
    workflow_description = template.description

    if clone_request:
        if clone_request.name:
            workflow_name = clone_request.name
        if clone_request.description:
            workflow_description = clone_request.description

    # Create new workflow from template
    workflow = Workflow(
        name=workflow_name,
        description=workflow_description,
        user_id=current_user.id,
        graph_definition=template.graph_definition.copy() if template.graph_definition else {"nodes": [], "edges": []},
        status=WorkflowStatus.DRAFT,
        global_variables={}
    )

    db.add(workflow)
    await db.flush()

    # Create initial version
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=1,
        graph_snapshot=workflow.graph_definition.copy(),
        description=f"Created from template: {template.name}"
    )
    db.add(version)
    await db.flush()

    workflow.active_version_id = version.id

    # Increment template clone count
    template.increment_clone_count()

    await db.commit()
    await db.refresh(workflow)

    logger.info(
        f"Template cloned: {template.id} -> {workflow.id}",
        extra={
            "user_id": str(current_user.id),
            "template_id": str(template.id),
            "template_name": template.name,
            "workflow_id": str(workflow.id)
        }
    )

    graph = workflow.graph_definition or {"nodes": [], "edges": []}

    return APIResponse(
        success=True,
        message=f"Successfully created workflow from template '{template.name}'",
        data=ClonedWorkflowResponse(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status.value,
            template_id=template.id,
            template_name=template.name,
            node_count=len(graph.get("nodes", [])),
            edge_count=len(graph.get("edges", [])),
            created_at=workflow.created_at
        )
    )


# ============================================================
# STATISTICS ENDPOINT
# ============================================================

@router.get(
    "/stats/summary",
    response_model=APIResponse[TemplateStatsResponse],
    summary="Get template statistics",
    description="Get aggregated statistics about available templates"
)
async def get_template_stats(
        db: AsyncSession = Depends(get_db)
):
    """
    Gets aggregated statistics about templates.

    Returns:
    - Total template count
    - Featured template count
    - Category breakdown
    - Total clones
    - Popular tags
    """
    # Get all public templates
    query = select(WorkflowTemplate).where(WorkflowTemplate.is_public == True)
    result = await db.execute(query)
    templates = result.scalars().all()

    total = len(templates)
    featured = sum(1 for t in templates if t.is_featured)
    total_clones = sum(t.clone_count for t in templates)

    # Count by category
    category_counts = Counter(t.category for t in templates)
    categories = [
        TemplateCategoryInfo(
            category=cat,
            count=category_counts.get(cat, 0),
            description=CATEGORY_DESCRIPTIONS.get(cat, "")
        )
        for cat in TemplateCategory
    ]
    categories.sort(key=lambda x: x.count, reverse=True)

    # Get popular tags
    all_tags = []
    for t in templates:
        if t.tags:
            all_tags.extend(t.tags)
    tag_counts = Counter(all_tags)
    popular_tags = [
        {"tag": tag, "count": count}
        for tag, count in tag_counts.most_common(10)
    ]

    return APIResponse(
        success=True,
        message="Template statistics retrieved",
        data=TemplateStatsResponse(
            total_templates=total,
            featured_templates=featured,
            categories=categories,
            total_clones=total_clones,
            popular_tags=popular_tags
        )
    )
