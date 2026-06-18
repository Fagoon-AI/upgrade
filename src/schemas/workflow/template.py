"""
Pydantic schemas for Workflow Template API.

Provides request/response validation for template management endpoints.
Templates are pre-built workflow configurations that users can clone.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict

from src.models.sql.workflow.template import TemplateCategory


# ============================================================
# CONFIGURATION
# ============================================================

MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2000
MAX_SHORT_DESCRIPTION_LENGTH = 255
MAX_TAGS = 20
MAX_TAG_LENGTH = 50


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class TemplateCloneRequest(BaseModel):
    """Schema for cloning a template to a new workflow."""
    name: Optional[str] = Field(
        default=None,
        max_length=MAX_NAME_LENGTH,
        description="Name for the new workflow (defaults to template name)"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Description for the new workflow"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validates and sanitizes workflow name."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)
        return v


class TemplateFilterParams(BaseModel):
    """Schema for template filtering parameters."""
    category: Optional[TemplateCategory] = Field(
        default=None,
        description="Filter by category"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Filter by tags (any match)"
    )
    difficulty: Optional[str] = Field(
        default=None,
        description="Filter by difficulty level"
    )
    is_featured: Optional[bool] = Field(
        default=None,
        description="Filter for featured templates only"
    )
    search: Optional[str] = Field(
        default=None,
        description="Search in name, description, and tags"
    )
    required_connections: Optional[List[str]] = Field(
        default=None,
        description="Filter by required connection providers"
    )


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class TemplateListResponse(BaseModel):
    """Schema for template listing (lightweight response)."""
    id: UUID
    name: str
    short_description: str
    category: TemplateCategory
    tags: List[str]
    icon: str
    difficulty: str
    estimated_setup_minutes: int
    is_featured: bool
    is_system_template: bool
    clone_count: int
    node_count: int
    required_connections: List[str]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_template(cls, template) -> "TemplateListResponse":
        """Creates list response from template model."""
        return cls(
            id=template.id,
            name=template.name,
            short_description=template.short_description,
            category=template.category,
            tags=template.tags or [],
            icon=template.icon,
            difficulty=template.difficulty,
            estimated_setup_minutes=template.estimated_setup_minutes,
            is_featured=template.is_featured,
            is_system_template=template.is_system_template,
            clone_count=template.clone_count,
            node_count=template.node_count,
            required_connections=template.required_connections or []
        )


class TemplateDetailResponse(BaseModel):
    """Schema for full template details."""
    id: UUID
    user_id: Optional[UUID]
    name: str
    description: str
    short_description: str
    category: TemplateCategory
    tags: List[str]
    graph_definition: Dict[str, Any]
    required_connections: List[str]
    icon: str
    difficulty: str
    estimated_setup_minutes: int
    is_featured: bool
    is_public: bool
    is_system_template: bool
    clone_count: int
    node_count: int
    edge_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_template(cls, template) -> "TemplateDetailResponse":
        """Creates detail response from template model."""
        graph = template.graph_definition or {"nodes": [], "edges": []}
        return cls(
            id=template.id,
            user_id=template.user_id,
            name=template.name,
            description=template.description,
            short_description=template.short_description,
            category=template.category,
            tags=template.tags or [],
            graph_definition=graph,
            required_connections=template.required_connections or [],
            icon=template.icon,
            difficulty=template.difficulty,
            estimated_setup_minutes=template.estimated_setup_minutes,
            is_featured=template.is_featured,
            is_public=template.is_public,
            is_system_template=template.is_system_template,
            clone_count=template.clone_count,
            node_count=len(graph.get("nodes", [])),
            edge_count=len(graph.get("edges", [])),
            created_at=template.created_at,
            updated_at=template.updated_at
        )


class TemplateCategoryInfo(BaseModel):
    """Schema for category information."""
    category: TemplateCategory
    count: int
    description: str


class TemplateStatsResponse(BaseModel):
    """Schema for template statistics."""
    total_templates: int
    featured_templates: int
    categories: List[TemplateCategoryInfo]
    total_clones: int
    popular_tags: List[Dict[str, Any]]


class ClonedWorkflowResponse(BaseModel):
    """Schema for the workflow created from a template clone."""
    id: UUID
    name: str
    description: Optional[str]
    status: str
    template_id: UUID
    template_name: str
    node_count: int
    edge_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
