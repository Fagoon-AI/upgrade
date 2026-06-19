import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from src.models.sql.workflow.workflow import WorkflowStatus


# ============================================================
# CONFIGURATION
# ============================================================

MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2000
MAX_NODES = 500
MAX_EDGES = 1000
MAX_NODE_ID_LENGTH = 100
MAX_GRAPH_SIZE_BYTES = 5 * 1024 * 1024  # 5MB


# ============================================================
# GRAPH STRUCTURES
# ============================================================

class Position(BaseModel):
    """Node position on canvas."""
    x: float = Field(default=0, ge=-10000, le=10000)
    y: float = Field(default=0, ge=-10000, le=10000)


class NodeData(BaseModel):
    """Node configuration data."""
    label: Optional[str] = Field(default=None, max_length=100)
    inputs: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class Node(BaseModel):
    """Workflow node definition."""
    id: str = Field(..., min_length=1, max_length=MAX_NODE_ID_LENGTH)
    type: str = Field(..., min_length=1, max_length=50)
    position: Position = Field(default_factory=Position)
    data: NodeData = Field(default_factory=NodeData)

    @property
    def resolved_type(self) -> str:
        """Gets the resolved backend node type."""
        if (self.type == "custom" or self.type == "customNode") and self.data:
            extra = getattr(self.data, "model_extra", None) or {}
            data_type = extra.get("type")
            if data_type:
                return data_type
        return self.type

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validates node ID format."""
        v = v.strip()

        # Only allow safe characters
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("Node ID can only contain letters, numbers, underscores, and hyphens")

        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validates node type format."""
        v = v.strip()

        if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*Node$', v) and v != "startNode":
            # Allow legacy formats
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
                raise ValueError("Invalid node type format")

        return v


class DataTransform(str, Enum):
    """Available data transforms for edge mappings."""
    JSON = "json"
    STRING = "string"
    FIRST_ITEM = "first_item"
    LAST_ITEM = "last_item"
    JOIN = "join"
    COUNT = "count"
    KEYS = "keys"
    VALUES = "values"
    TRIM = "trim"
    LOWERCASE = "lowercase"
    UPPERCASE = "uppercase"
    FLATTEN = "flatten"
    UNIQUE = "unique"
    SORT = "sort"
    REVERSE = "reverse"


class DataMapping(BaseModel):
    """
    Maps a source field to a target field with optional transform.

    This is the core unit of visual data flow - when a user draws a connection
    and configures which fields to map, this schema captures that mapping.

    Examples:
        - Simple: source_field="output" → target_field="input"
        - Nested: source_field="data.results" → target_field="items"
        - With transform: source_field="text" → target_field="content", transform="trim"
    """
    source_field: str = Field(
        default="output",
        max_length=200,
        description="Dot-notation path in source node output (e.g., 'data.results[0].text')"
    )
    target_field: str = Field(
        default="input",
        max_length=200,
        description="Target input field name"
    )
    transform: Optional[DataTransform] = Field(
        default=None,
        description="Optional transform to apply during data transfer"
    )
    default_value: Optional[Any] = Field(
        default=None,
        description="Fallback value if source field is missing or null"
    )

    @field_validator("source_field", "target_field")
    @classmethod
    def validate_field_paths(cls, v: str) -> str:
        """Validates field path format."""
        v = v.strip()
        # Allow dot notation, brackets for arrays, and wildcards
        if not re.match(r'^[\w\.\[\]\*]+$', v):
            raise ValueError("Field path can only contain letters, numbers, dots, brackets, and wildcards")
        return v


class MergeStrategy(str, Enum):
    """Strategy for merging multiple inputs to the same handle."""
    CONCATENATE = "concatenate"  # Join strings with separator
    ARRAY = "array"              # Collect into array
    MERGE_DICT = "merge_dict"    # Merge dictionaries
    FIRST = "first"              # Take first value
    LAST = "last"                # Take last value


class Edge(BaseModel):
    """
    Workflow edge definition with visual data flow support.

    Edges represent connections between nodes. They can carry:
    1. Simple connections (just connects two nodes, passes full output)
    2. Mapped connections (specific field-to-field mappings with transforms)

    The data_mappings field enables the "connect the dots" visual experience
    where users can configure exactly how data flows between nodes.
    """
    id: str = Field(..., min_length=1, max_length=MAX_NODE_ID_LENGTH)
    source: str = Field(..., min_length=1, max_length=MAX_NODE_ID_LENGTH)
    target: str = Field(..., min_length=1, max_length=MAX_NODE_ID_LENGTH)
    sourceHandle: Optional[str] = Field(
        default="output",
        max_length=50,
        description="Output handle on source node"
    )
    targetHandle: Optional[str] = Field(
        default="input",
        max_length=50,
        description="Input handle on target node"
    )

    # Visual Data Flow Configuration
    data_mappings: List[DataMapping] = Field(
        default_factory=list,
        max_length=50,
        description="Field-level mappings for this edge (visual data flow)"
    )
    merge_strategy: Optional[MergeStrategy] = Field(
        default=None,
        description="How to merge if multiple edges target the same input"
    )

    # Auto-mapping configuration
    auto_map: bool = Field(
        default=True,
        description="Automatically map matching field names"
    )

    # Edge metadata for UI
    label: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional label shown on the edge"
    )
    animated: bool = Field(
        default=False,
        description="Whether to animate this edge in the UI"
    )

    @field_validator("id", "source", "target")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validates edge ID format."""
        v = v.strip()

        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("ID can only contain letters, numbers, underscores, and hyphens")

        return v


class Viewport(BaseModel):
    """Canvas viewport state."""
    x: float = Field(default=0)
    y: float = Field(default=0)
    zoom: float = Field(default=1, ge=0.1, le=4)


class WorkflowGraph(BaseModel):
    """
    Complete workflow graph definition.

    Validates:
    - Node count limits
    - Edge count limits
    - Edge references valid nodes
    - Single start node
    - No orphan nodes (warning)
    """
    nodes: List[Node] = Field(default_factory=list, max_length=MAX_NODES)
    edges: List[Edge] = Field(default_factory=list, max_length=MAX_EDGES)
    viewport: Optional[Viewport] = Field(default_factory=Viewport)

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowGraph":
        """Validates graph structure."""
        # Get node IDs
        node_ids = {node.id for node in self.nodes}

        # Validate edges reference existing nodes
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' references non-existent node")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' references non-existent node")

        # Check for duplicate node IDs
        if len(node_ids) != len(self.nodes):
            raise ValueError("Duplicate node IDs detected")

        # Check for duplicate edge IDs
        edge_ids = [edge.id for edge in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Duplicate edge IDs detected")

        return self

    def get_start_nodes(self) -> List[Node]:
        """Gets all start nodes."""
        return [n for n in self.nodes if n.resolved_type == "startNode"]

    def get_node_by_id(self, node_id: str) -> Optional[Node]:
        """Gets node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None


# ============================================================
# API REQUEST SCHEMAS
# ============================================================

class WorkflowCreate(BaseModel):
    """Schema for creating a workflow."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=MAX_NAME_LENGTH,
        description="Workflow name"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Workflow description"
    )
    graph_definition: Optional[WorkflowGraph] = Field(
        default=None,
        description="Initial graph definition"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validates and sanitizes name."""
        v = v.strip()

        if not v:
            raise ValueError("Name cannot be empty")

        # Remove potentially dangerous characters
        v = re.sub(r'[<>{}[\]\\]', '', v)

        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        """Validates and sanitizes description."""
        if not v:
            return None

        v = v.strip()
        return v if v else None


class WorkflowUpdate(BaseModel):
    """Schema for updating a workflow."""
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_NAME_LENGTH
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH
    )
    graph_definition: Optional[WorkflowGraph] = None
    status: Optional[WorkflowStatus] = None
    global_variables: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validates name if provided."""
        if v is None:
            return None

        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")

        v = re.sub(r'[<>{}[\]\\]', '', v)
        return v


class WorkflowClone(BaseModel):
    """Schema for cloning a workflow."""
    new_name: Optional[str] = Field(
        default=None,
        max_length=MAX_NAME_LENGTH,
        description="Name for the cloned workflow"
    )


class WorkflowImport(BaseModel):
    """Schema for importing a workflow."""
    name: Optional[str] = Field(
        default=None,
        max_length=MAX_NAME_LENGTH
    )
    description: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH
    )
    graph_definition: WorkflowGraph = Field(
        ...,
        description="Graph definition to import"
    )
    global_variables: Optional[Dict[str, Any]] = None


# ============================================================
# API RESPONSE SCHEMAS
# ============================================================

class WorkflowResponse(BaseModel):
    """Schema for workflow API response."""
    id: UUID
    name: str
    description: Optional[str]
    status: WorkflowStatus
    version: int
    active_version_id: Optional[UUID] = None
    node_count: int = 0
    edge_count: int = 0
    is_runnable: bool = False
    graph_definition: WorkflowGraph
    global_variables: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_workflow(cls, workflow) -> "WorkflowResponse":
        """Creates response from workflow model."""
        graph = workflow.graph_definition or {"nodes": [], "edges": []}

        return cls(
            id=workflow.id,
            name=workflow.name,
            description=workflow.description,
            status=workflow.status,
            version=workflow.version,
            active_version_id=workflow.active_version_id,
            node_count=len(graph.get("nodes", [])),
            edge_count=len(graph.get("edges", [])),
            is_runnable=workflow.status == WorkflowStatus.PUBLISHED and workflow.active_version_id is not None,
            graph_definition=WorkflowGraph.model_validate(graph),
            global_variables=workflow.global_variables,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at
        )


class WorkflowListResponse(BaseModel):
    """Schema for workflow list item."""
    id: UUID
    name: str
    description: Optional[str]
    status: WorkflowStatus
    version: int
    node_count: int = 0
    is_runnable: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowVersionResponse(BaseModel):
    """Schema for workflow version."""
    id: UUID
    version_number: int
    description: Optional[str]
    node_count: int = 0
    edge_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowValidationResponse(BaseModel):
    """Schema for validation result."""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class WorkflowExportResponse(BaseModel):
    """Schema for exported workflow."""
    format_version: str = "1.0"
    exported_at: datetime
    name: str
    description: Optional[str]
    graph_definition: Dict[str, Any]
    global_variables: Optional[Dict[str, Any]] = None
    versions: Optional[List[Dict[str, Any]]] = None