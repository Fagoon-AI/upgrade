import uuid
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import DateTime, String, Index, Integer, text, Enum as SAEnum
from pydantic import field_validator

if TYPE_CHECKING:
    from src.models.sql.workflow.user import User
    from src.models.sql.workflow.execution import WorkflowExecution
    from src.models.sql.workflow.version import WorkflowVersion
    from src.models.sql.workflow.schedule import WorkflowSchedule


class WorkflowStatus(str, Enum):
    """Workflow lifecycle status."""
    DRAFT = "DRAFT"           # Work in progress
    PUBLISHED = "PUBLISHED"   # Ready for execution
    ARCHIVED = "ARCHIVED"     # Soft deleted
    DISABLED = "DISABLED"     # Temporarily disabled


# Valid status transitions
STATUS_TRANSITIONS = {
    WorkflowStatus.DRAFT: {WorkflowStatus.PUBLISHED, WorkflowStatus.ARCHIVED},
    WorkflowStatus.PUBLISHED: {WorkflowStatus.DRAFT, WorkflowStatus.ARCHIVED, WorkflowStatus.DISABLED},
    WorkflowStatus.ARCHIVED: {WorkflowStatus.DRAFT},
    WorkflowStatus.DISABLED: {WorkflowStatus.PUBLISHED, WorkflowStatus.ARCHIVED},
}


class Workflow(SQLModel, table=True):
    """
    Workflow model representing a DAG of nodes.

    Features:
    - UUID primary key
    - User ownership (foreign key)
    - JSON graph definition (JSONB in Postgres)
    - Status lifecycle management
    - Version tracking
    - Global variables for runtime configuration
    - Audit timestamps

    Indexes:
    - Primary key on id
    - Foreign key index on user_id
    - Index on status for filtering
    - Composite index on (user_id, status) for common queries
    """

    __tablename__ = "workflow"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique workflow identifier"
    )

    # Ownership
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        index=True,
        description="Owner user ID"
    )

    # Basic info
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
        description="Workflow name"
    )

    description: Optional[str] = Field(
        default=None,
        sa_column=Column(String(2000)),
        description="Workflow description"
    )

    # Graph definition (JSONB in Postgres)
    graph_definition: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
        description="DAG structure (nodes and edges)"
    )

    # Status
    status: WorkflowStatus = Field(
        default=WorkflowStatus.DRAFT,
        sa_column=Column(
            SAEnum(WorkflowStatus, name="workflowstatus", create_type=False),
            nullable=False,
            default=WorkflowStatus.DRAFT,
            index=True
        ),
        description="Workflow lifecycle status"
    )

    # Versioning
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, default=1),
        description="Optimistic locking version"
    )

    active_version_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Currently active version ID"
    )

    # Configuration
    global_variables: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Runtime configuration variables"
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

    # Relationships
    user: "User" = Relationship(back_populates="workflows")

    executions: List["WorkflowExecution"] = Relationship(
        back_populates="workflow",
        sa_relationship_kwargs={"lazy": "dynamic"}
    )

    versions: List["WorkflowVersion"] = Relationship(
        back_populates="workflow",
        sa_relationship_kwargs={"lazy": "selectin", "order_by": "WorkflowVersion.version_number.desc()"}
    )

    schedules: List["WorkflowSchedule"] = Relationship(
        back_populates="workflow",
        sa_relationship_kwargs={"lazy": "selectin"}
    )

    # Table configuration
    __table_args__ = (
        Index("ix_workflow_user_status", "user_id", "status"),
        Index("ix_workflow_user_updated", "user_id", "updated_at"),
    )

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validates and sanitizes workflow name."""
        if not v:
            raise ValueError("Workflow name is required")

        v = v.strip()

        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)

        if len(v) < 1:
            raise ValueError("Workflow name cannot be empty")

        if len(v) > 255:
            raise ValueError("Workflow name too long (max 255 characters)")

        return v

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        """Validates and sanitizes description."""
        if not v:
            return None

        v = v.strip()

        if len(v) > 2000:
            v = v[:2000]

        return v if v else None

    @field_validator("graph_definition", mode="before")
    @classmethod
    def validate_graph(cls, v: Any) -> Dict[str, Any]:
        """Ensures graph definition is valid."""
        if v is None:
            return {"nodes": [], "edges": [], "viewport": {}}

        if not isinstance(v, dict):
            raise ValueError("Graph definition must be a dictionary")

        # Ensure required keys exist
        if "nodes" not in v:
            v["nodes"] = []

        if "edges" not in v:
            v["edges"] = []

        if "viewport" not in v:
            v["viewport"] = {}

        return v

    # ============================================================
    # METHODS
    # ============================================================

    def can_transition_to(self, new_status: WorkflowStatus) -> bool:
        """
        Checks if status transition is valid.

        Args:
            new_status: Target status

        Returns:
            True if transition is allowed
        """
        allowed = STATUS_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    def transition_to(self, new_status: WorkflowStatus) -> None:
        """
        Transitions to new status with validation.

        Args:
            new_status: Target status

        Raises:
            ValueError: If transition is not allowed
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Cannot transition from {self.status.value} to {new_status.value}"
            )

        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    @property
    def is_runnable(self) -> bool:
        """Checks if workflow can be executed."""
        return (
                self.status == WorkflowStatus.PUBLISHED and
                self.active_version_id is not None and
                len(self.graph_definition.get("nodes", [])) > 0
        )

    @property
    def node_count(self) -> int:
        """Gets number of nodes in the graph."""
        return len(self.graph_definition.get("nodes", []))

    @property
    def edge_count(self) -> int:
        """Gets number of edges in the graph."""
        return len(self.graph_definition.get("edges", []))

    def get_node_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets a node from the graph by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node definition or None
        """
        for node in self.graph_definition.get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None

    def get_start_node(self) -> Optional[Dict[str, Any]]:
        """Gets the start node of the workflow."""
        for node in self.graph_definition.get("nodes", []):
            if node.get("type") == "startNode":
                return node
        return None

    def to_dict(self, include_graph: bool = True) -> Dict[str, Any]:
        """
        Converts workflow to dictionary.

        Args:
            include_graph: Include full graph definition

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "version": self.version,
            "active_version_id": str(self.active_version_id) if self.active_version_id else None,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "is_runnable": self.is_runnable,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_graph:
            data["graph_definition"] = self.graph_definition
            data["global_variables"] = self.global_variables

        return data

    def __repr__(self) -> str:
        return f"<Workflow {self.name} ({self.status.value})>"

    def __str__(self) -> str:
        return self.name