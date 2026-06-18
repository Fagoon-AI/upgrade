import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import DateTime, String, Index, Integer, text

if TYPE_CHECKING:
    from src.models.sql.workflow.workflow import Workflow


class WorkflowVersion(SQLModel, table=True):
    """
    Immutable workflow version snapshot.

    Features:
    - UUID primary key
    - Workflow relationship
    - Sequential version numbering
    - Immutable graph snapshot
    - Version description/changelog
    - Creation timestamp

    Purpose:
    - Track workflow history
    - Enable rollback
    - Execution reproducibility
    - Audit trail

    Indexes:
    - Primary key on id
    - Foreign key index on workflow_id
    - Unique constraint on (workflow_id, version_number)
    """

    __tablename__ = "workflowversion"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique version identifier"
    )

    # Relationship
    workflow_id: uuid.UUID = Field(
        foreign_key="workflow.id",
        index=True,
        description="Parent workflow ID"
    )

    # Version info
    version_number: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
        description="Sequential version number (1, 2, 3, ...)"
    )

    # Immutable snapshot
    graph_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
        description="Immutable copy of graph at version time"
    )

    # Metadata
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500)),
        description="Version description/changelog"
    )

    # Author tracking (optional)
    created_by: Optional[uuid.UUID] = Field(
        default=None,
        description="User who created this version"
    )

    # Timestamp
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Version creation timestamp"
    )

    # Relationships
    workflow: "Workflow" = Relationship(back_populates="versions")

    # Table configuration
    __table_args__ = (
        Index(
            "ix_version_workflow_number",
            "workflow_id",
            "version_number",
            unique=True
        ),
    )

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def node_count(self) -> int:
        """Gets number of nodes in this version."""
        return len(self.graph_snapshot.get("nodes", []))

    @property
    def edge_count(self) -> int:
        """Gets number of edges in this version."""
        return len(self.graph_snapshot.get("edges", []))

    @property
    def version_label(self) -> str:
        """Gets human-readable version label."""
        return f"v{self.version_number}"

    # ============================================================
    # METHODS
    # ============================================================

    def get_node_ids(self) -> set:
        """
        Gets set of node IDs in this version.

        Returns:
            Set of node ID strings
        """
        nodes = self.graph_snapshot.get("nodes", [])
        return {n.get("id") for n in nodes if n.get("id")}

    def get_node_types(self) -> set:
        """
        Gets set of node types in this version.

        Returns:
            Set of node type strings
        """
        nodes = self.graph_snapshot.get("nodes", [])
        return {n.get("type") for n in nodes if n.get("type")}

    def compare_to(self, other: "WorkflowVersion") -> Dict[str, Any]:
        """
        Compares this version to another.

        Args:
            other: Another WorkflowVersion to compare

        Returns:
            Dictionary with comparison results
        """
        self_nodes = self.get_node_ids()
        other_nodes = other.get_node_ids()

        return {
            "from_version": self.version_number,
            "to_version": other.version_number,
            "nodes_added": list(other_nodes - self_nodes),
            "nodes_removed": list(self_nodes - other_nodes),
            "nodes_unchanged": list(self_nodes & other_nodes),
            "from_node_count": len(self_nodes),
            "to_node_count": len(other_nodes),
            "from_edge_count": self.edge_count,
            "to_edge_count": other.edge_count,
        }

    def to_dict(self, include_graph: bool = False) -> Dict[str, Any]:
        """
        Converts version to dictionary.

        Args:
            include_graph: Include full graph snapshot

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "version_number": self.version_number,
            "version_label": self.version_label,
            "description": self.description,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": str(self.created_by) if self.created_by else None,
        }

        if include_graph:
            data["graph_snapshot"] = self.graph_snapshot

        return data

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Converts to minimal summary dictionary.

        Returns:
            Minimal dictionary for listings
        """
        return {
            "id": str(self.id),
            "version_number": self.version_number,
            "version_label": self.version_label,
            "description": self.description,
            "node_count": self.node_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<WorkflowVersion {self.version_label}>"

    def __str__(self) -> str:
        desc = f" - {self.description}" if self.description else ""
        return f"{self.version_label}{desc}"