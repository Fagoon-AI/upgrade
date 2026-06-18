import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import DateTime, String, Index, Integer, text, Enum as SAEnum

if TYPE_CHECKING:
    from src.models.sql.workflow.workflow import Workflow


class ExecutionStatus(str, Enum):
    """Execution lifecycle status."""
    PENDING = "PENDING"       # Queued, waiting to start
    RUNNING = "RUNNING"       # Currently executing
    COMPLETED = "COMPLETED"   # Successfully finished
    FAILED = "FAILED"         # Execution failed
    PAUSED = "PAUSED"         # Waiting for HITL approval
    CANCELLED = "CANCELLED"   # Manually cancelled
    TIMEOUT = "TIMEOUT"       # Timed out


# Terminal states
TERMINAL_STATES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.TIMEOUT
}


class WorkflowExecution(SQLModel, table=True):
    """
    Workflow execution record.

    Features:
    - UUID primary key
    - Workflow relationship
    - Status tracking
    - Graph snapshot (immutable copy at execution time)
    - Context data (node outputs)
    - Results storage
    - Idempotency key for deduplication
    - Timing information

    Indexes:
    - Primary key on id
    - Foreign key index on workflow_id
    - Index on status for filtering
    - Unique index on external_event_id for idempotency
    - Composite index for common queries
    """

    __tablename__ = "workflowexecution"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique execution identifier"
    )

    # Relationships
    workflow_id: uuid.UUID = Field(
        foreign_key="workflow.id",
        index=True,
        description="Parent workflow ID"
    )

    version_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="workflowversion.id",
        index=True,
        description="Workflow version at execution time"
    )

    # Trigger info
    trigger_type: str = Field(
        default="MANUAL",
        sa_column=Column(String(50), nullable=False, default="MANUAL"),
        description="How execution was triggered (MANUAL, WEBHOOK, SCHEDULE, API)"
    )

    # Status
    status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING,
        sa_column=Column(
            SAEnum(ExecutionStatus, name="executionstatus", create_type=False),
            nullable=False,
            default=ExecutionStatus.PENDING,
            index=True
        ),
        description="Execution status"
    )

    # Graph snapshot
    graph_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Immutable graph copy at execution time"
    )

    # Runtime data
    context_data: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Node outputs and intermediate state"
    )

    results: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Final execution results"
    )

    # Idempotency
    external_event_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), unique=True, index=True),
        description="External event ID for deduplication"
    )

    # Timing
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Execution start time"
    )

    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Execution end time"
    )

    # Relationships
    workflow: "Workflow" = Relationship(back_populates="executions")

    traces: List["NodeExecutionTrace"] = Relationship(
        back_populates="execution",
        sa_relationship_kwargs={"lazy": "dynamic", "order_by": "NodeExecutionTrace.created_at"}
    )

    # Table configuration
    __table_args__ = (
        Index("ix_execution_workflow_status", "workflow_id", "status"),
        Index("ix_execution_workflow_started", "workflow_id", "started_at"),
        Index("ix_execution_status_started", "status", "started_at"),
    )

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_terminal(self) -> bool:
        """Checks if execution is in a terminal state."""
        return self.status in TERMINAL_STATES

    @property
    def is_running(self) -> bool:
        """Checks if execution is currently running."""
        return self.status == ExecutionStatus.RUNNING

    @property
    def is_success(self) -> bool:
        """Checks if execution completed successfully."""
        return self.status == ExecutionStatus.COMPLETED

    @property
    def duration_ms(self) -> Optional[int]:
        """Gets execution duration in milliseconds."""
        if not self.started_at:
            return None

        end_time = self.finished_at or datetime.now(timezone.utc)
        delta = end_time - self.started_at
        return int(delta.total_seconds() * 1000)

    @property
    def error_message(self) -> Optional[str]:
        """Gets error message if execution failed."""
        if self.status != ExecutionStatus.FAILED:
            return None
        return self.context_data.get("error")

    # ============================================================
    # METHODS
    # ============================================================

    def get_node_output(self, node_id: str) -> Optional[Any]:
        """
        Gets output for a specific node.

        Args:
            node_id: Node identifier

        Returns:
            Node output or None
        """
        return self.context_data.get(node_id)

    def set_node_output(self, node_id: str, output: Any) -> None:
        """
        Sets output for a specific node.

        Args:
            node_id: Node identifier
            output: Node output data
        """
        if self.context_data is None:
            self.context_data = {}
        self.context_data[node_id] = output

    def mark_running(self) -> None:
        """Marks execution as running."""
        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, results: Optional[Dict[str, Any]] = None) -> None:
        """Marks execution as completed."""
        self.status = ExecutionStatus.COMPLETED
        self.finished_at = datetime.now(timezone.utc)
        if results:
            self.results = results

    def mark_failed(self, error: str) -> None:
        """Marks execution as failed."""
        self.status = ExecutionStatus.FAILED
        self.finished_at = datetime.now(timezone.utc)
        if self.context_data is None:
            self.context_data = {}
        self.context_data["error"] = error

    def mark_paused(self, reason: str = "Awaiting approval") -> None:
        """Marks execution as paused."""
        self.status = ExecutionStatus.PAUSED
        if self.context_data is None:
            self.context_data = {}
        self.context_data["pause_reason"] = reason

    def to_dict(self, include_context: bool = False) -> Dict[str, Any]:
        """
        Converts execution to dictionary.

        Args:
            include_context: Include full context data

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "version_id": str(self.version_id) if self.version_id else None,
            "trigger_type": self.trigger_type,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "is_terminal": self.is_terminal,
        }

        if self.status == ExecutionStatus.FAILED:
            data["error"] = self.error_message

        if self.status == ExecutionStatus.COMPLETED:
            data["results"] = self.results

        if include_context:
            data["context_data"] = self.context_data
            data["graph_snapshot"] = self.graph_snapshot

        return data

    def __repr__(self) -> str:
        return f"<WorkflowExecution {self.id} ({self.status.value})>"


class NodeExecutionTrace(SQLModel, table=True):
    """
    Individual node execution trace for observability.

    Features:
    - UUID primary key
    - Execution relationship
    - Node identification
    - Input/output capture
    - Timing and status
    - Error tracking
    - Retry tracking
    """

    __tablename__ = "nodeexecutiontrace"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique trace identifier"
    )

    # Relationships
    execution_id: uuid.UUID = Field(
        foreign_key="workflowexecution.id",
        index=True,
        description="Parent execution ID"
    )

    # Node identification
    node_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
        description="Node identifier in graph"
    )

    node_type: str = Field(
        sa_column=Column(String(100), nullable=False),
        description="Node type (e.g., gmailNode, agentNode)"
    )

    # Execution data
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Node input data"
    )

    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, default=dict),
        description="Node output data"
    )

    # Status
    status: str = Field(
        sa_column=Column(String(20), nullable=False),
        description="SUCCESS, FAILED, SKIPPED"
    )

    error_message: Optional[str] = Field(
        default=None,
        sa_column=Column(String(2000)),
        description="Error message if failed"
    )

    # Timing
    duration_ms: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, default=0),
        description="Execution duration in milliseconds"
    )

    # Retry tracking
    attempt_number: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, default=1),
        description="Attempt number (1 = first try)"
    )

    # Timestamp
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Trace creation time"
    )

    # Relationships
    execution: WorkflowExecution = Relationship(back_populates="traces")

    # Table configuration
    __table_args__ = (
        Index("ix_trace_execution_created", "execution_id", "created_at"),
        Index("ix_trace_node_status", "node_id", "status"),
    )

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_success(self) -> bool:
        """Checks if trace represents successful execution."""
        return self.status == "SUCCESS"

    @property
    def is_retry(self) -> bool:
        """Checks if this was a retry attempt."""
        return self.attempt_number > 1

    # ============================================================
    # METHODS
    # ============================================================

    def to_dict(self, include_data: bool = True) -> Dict[str, Any]:
        """
        Converts trace to dictionary.

        Args:
            include_data: Include inputs/outputs

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "execution_id": str(self.execution_id),
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "attempt_number": self.attempt_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if self.error_message:
            data["error_message"] = self.error_message

        if include_data:
            data["inputs"] = self.inputs
            data["outputs"] = self.outputs

        return data

    def __repr__(self) -> str:
        return f"<NodeTrace {self.node_id} ({self.status})>"