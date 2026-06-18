"""
Workflow Template Model.

Stores reusable workflow templates that users can clone to create new workflows.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlmodel import SQLModel, Field, JSON, Column
from sqlalchemy import DateTime, String, Index, Integer, text, Boolean, Enum as SAEnum


class TemplateCategory(str, Enum):
    """Template categories for organization."""
    AI_AUTOMATION = "AI Automation"
    DATA_PROCESSING = "Data Processing"
    COMMUNICATION = "Communication"
    MARKETING = "Marketing"
    CUSTOMER_SUPPORT = "Customer Support"
    DEVELOPMENT = "Development"
    PRODUCTIVITY = "Productivity"
    ANALYTICS = "Analytics"
    STARTER = "Getting Started"


class WorkflowTemplate(SQLModel, table=True):
    """
    Workflow Template Model.

    Features:
    - UUID primary key
    - Categorization and tagging
    - Usage tracking (clone count)
    - Featured flag for promotion
    - Graph definition (template DAG)
    - Required integrations listing

    Templates can be:
    - System templates (created by platform, user_id is null)
    - User templates (created by users, has user_id)
    """

    __tablename__ = "workflow_template"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique template identifier"
    )

    # Optional user ownership (null for system templates)
    user_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="user.id",
        index=True,
        description="Creator user ID (null for system templates)"
    )

    # Basic info
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Template name"
    )

    description: str = Field(
        sa_column=Column(String(2000), nullable=False),
        description="Template description"
    )

    short_description: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Short description for listings"
    )

    # Categorization
    category: TemplateCategory = Field(
        default=TemplateCategory.STARTER,
        sa_column=Column(
            SAEnum(TemplateCategory, name="templatecategory", create_type=False),
            nullable=False,
            default=TemplateCategory.STARTER,
            index=True
        ),
        description="Template category"
    )

    tags: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, default=list),
        description="Searchable tags"
    )

    # Graph definition
    graph_definition: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
        description="Template DAG structure"
    )

    # Required integrations/connections
    required_connections: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, default=list),
        description="Required connection providers (e.g., ['OPENAI', 'SLACK'])"
    )

    # Metadata
    icon: str = Field(
        default="Workflow",
        sa_column=Column(String(50), nullable=False, default="Workflow"),
        description="Icon name for display"
    )

    difficulty: str = Field(
        default="beginner",
        sa_column=Column(String(20), nullable=False, default="beginner"),
        description="Difficulty level (beginner, intermediate, advanced)"
    )

    estimated_setup_minutes: int = Field(
        default=5,
        sa_column=Column(Integer, nullable=False, default=5),
        description="Estimated setup time in minutes"
    )

    # Promotion
    is_featured: bool = Field(
        default=False,
        sa_column=Column(Boolean, default=False, index=True),
        description="Featured template flag"
    )

    is_public: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, index=True),
        description="Public visibility"
    )

    # Usage tracking
    clone_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
        description="Number of times cloned"
    )

    # Audit timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Creation timestamp"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=lambda: datetime.now(timezone.utc)
        ),
        description="Last update timestamp"
    )

    # Table configuration
    __table_args__ = (
        Index("ix_template_category_featured", "category", "is_featured"),
        Index("ix_template_public_featured", "is_public", "is_featured"),
        Index("ix_template_clone_count", "clone_count"),
    )

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_system_template(self) -> bool:
        """Checks if this is a system template."""
        return self.user_id is None

    @property
    def node_count(self) -> int:
        """Gets number of nodes in the template."""
        return len(self.graph_definition.get("nodes", []))

    # ============================================================
    # METHODS
    # ============================================================

    def increment_clone_count(self) -> None:
        """Increments the clone count."""
        self.clone_count += 1
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self, include_graph: bool = True) -> Dict[str, Any]:
        """Converts template to dictionary."""
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "name": self.name,
            "description": self.description,
            "short_description": self.short_description,
            "category": self.category.value,
            "tags": self.tags,
            "required_connections": self.required_connections,
            "icon": self.icon,
            "difficulty": self.difficulty,
            "estimated_setup_minutes": self.estimated_setup_minutes,
            "is_featured": self.is_featured,
            "is_public": self.is_public,
            "is_system_template": self.is_system_template,
            "clone_count": self.clone_count,
            "node_count": self.node_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_graph:
            data["graph_definition"] = self.graph_definition

        return data

    def to_listing_dict(self) -> Dict[str, Any]:
        """Converts to minimal dictionary for listings."""
        return {
            "id": str(self.id),
            "name": self.name,
            "short_description": self.short_description,
            "category": self.category.value,
            "tags": self.tags,
            "icon": self.icon,
            "difficulty": self.difficulty,
            "is_featured": self.is_featured,
            "clone_count": self.clone_count,
            "node_count": self.node_count,
            "required_connections": self.required_connections,
        }

    def __repr__(self) -> str:
        return f"<WorkflowTemplate {self.name}>"

    def __str__(self) -> str:
        return self.name
