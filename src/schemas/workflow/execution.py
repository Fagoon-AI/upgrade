from datetime import datetime
from typing import Optional, Any, Dict, List, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict

from src.models.sql.workflow.execution import ExecutionStatus


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class ExecutionRunRequest(BaseModel):
    """Schema for starting an execution."""
    initial_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Initial input data for the workflow"
    )
    async_mode: bool = Field(
        default=True,
        description="Run asynchronously (default) or wait for completion"
    )
    timeout_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        le=3600,
        description="Timeout for sync mode (max 1 hour)"
    )

    @field_validator("initial_input")
    @classmethod
    def validate_input(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validates initial input."""
        if v is None:
            return {}

        # Check for reasonable size (5MB limit)
        import json
        try:
            size = len(json.dumps(v))
            if size > 5 * 1024 * 1024:
                raise ValueError("Initial input too large (max 5MB)")
        except (TypeError, ValueError) as e:
            if "too large" in str(e):
                raise
            # JSON serialization failed - will be caught later
            pass

        return v


class ExecutionResumeRequest(BaseModel):
    """Schema for resuming a paused execution."""
    action: str = Field(
        default="approve",
        description="Resume action (approve, reject, continue)"
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional comment from approver"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional data to pass to resumed node"
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validates resume action."""
        v = v.lower().strip()

        allowed = {"approve", "reject", "continue", "cancel"}
        if v not in allowed:
            raise ValueError(f"Action must be one of: {', '.join(allowed)}")

        return v


class ExecutionCancelRequest(BaseModel):
    """Schema for cancelling an execution."""
    reason: Optional[str] = Field(
        default="Cancelled by user",
        max_length=500,
        description="Cancellation reason"
    )


class ExecutionRetryRequest(BaseModel):
    """Schema for retrying a failed execution."""
    override_input: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Override initial input for retry"
    )


class ExecutionFilterRequest(BaseModel):
    """Schema for filtering executions."""
    workflow_id: Optional[UUID] = None
    status: Optional[ExecutionStatus] = None
    trigger_type: Optional[str] = None
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger(cls, v: Optional[str]) -> Optional[str]:
        """Validates trigger type."""
        if v is None:
            return None

        v = v.upper()
        allowed = {"MANUAL", "WEBHOOK", "SCHEDULE", "API"}
        if v not in allowed:
            raise ValueError(f"Trigger must be one of: {', '.join(allowed)}")

        return v


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class ExecutionBase(BaseModel):
    """Base schema for execution fields."""
    id: UUID
    workflow_id: UUID
    status: ExecutionStatus
    trigger_type: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExecutionResponse(ExecutionBase):
    """
    Optimized for lists/history.
    Excludes heavy context data.
    """
    duration_ms: Optional[int] = None
    version_id: Optional[UUID] = None

    @classmethod
    def from_execution(cls, execution) -> "ExecutionResponse":
        """Creates response from execution model."""
        duration_ms = None
        if execution.started_at:
            end_time = execution.finished_at or datetime.now()
            duration_ms = int((end_time - execution.started_at).total_seconds() * 1000)

        return cls(
            id=execution.id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            trigger_type=execution.trigger_type,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            duration_ms=duration_ms,
            version_id=execution.version_id
        )


class ExecutionStatusResponse(ExecutionBase):
    """
    Detailed status response.
    Includes results and error information.
    """
    duration_ms: Optional[int] = None
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None

    @classmethod
    def from_execution(cls, execution) -> "ExecutionStatusResponse":
        """Creates status response from execution model."""
        duration_ms = None
        if execution.started_at:
            end_time = execution.finished_at or datetime.now()
            duration_ms = int((end_time - execution.started_at).total_seconds() * 1000)

        error = None
        if execution.status == ExecutionStatus.FAILED:
            error = (execution.context_data or {}).get("error")

        return cls(
            id=execution.id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            trigger_type=execution.trigger_type,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            duration_ms=duration_ms,
            results=execution.results if execution.status == ExecutionStatus.COMPLETED else None,
            error=error
        )


class ExecutionStartResponse(BaseModel):
    """Response for execution start."""
    execution_id: UUID
    status: ExecutionStatus
    message: str = "Execution started"


class ExecutionBulkStatusResponse(BaseModel):
    """Response for bulk status check."""
    executions: Dict[str, ExecutionStatusResponse]
    not_found: List[str] = Field(default_factory=list)


# ============================================================
# TRACE SCHEMAS
# ============================================================

class NodeTraceResponse(BaseModel):
    """
    Detailed output for a single node's execution.
    """
    id: UUID
    node_id: str
    node_type: str
    status: str
    duration_ms: int
    attempt_number: int = 1
    created_at: datetime

    # Detailed data (optional)
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_trace(cls, trace, include_data: bool = True) -> "NodeTraceResponse":
        """Creates response from trace model."""
        return cls(
            id=trace.id,
            node_id=trace.node_id,
            node_type=trace.node_type,
            status=trace.status,
            duration_ms=trace.duration_ms,
            attempt_number=trace.attempt_number,
            created_at=trace.created_at,
            inputs=trace.inputs if include_data else None,
            outputs=trace.outputs if include_data else None,
            error_message=trace.error_message
        )


class ExecutionTimelineResponse(BaseModel):
    """
    Full chronological sequence of an execution's node results.
    """
    execution_id: UUID
    workflow_id: UUID
    status: ExecutionStatus
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    total_duration_ms: int = 0
    node_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    traces: List[NodeTraceResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_execution(
            cls,
            execution,
            traces: List,
            include_trace_data: bool = True
    ) -> "ExecutionTimelineResponse":
        """Creates timeline from execution and traces."""
        trace_responses = [
            NodeTraceResponse.from_trace(t, include_trace_data)
            for t in traces
        ]

        return cls(
            execution_id=execution.id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
            total_duration_ms=sum(t.duration_ms for t in trace_responses),
            node_count=len(trace_responses),
            success_count=sum(1 for t in trace_responses if t.status == "SUCCESS"),
            failed_count=sum(1 for t in trace_responses if t.status == "FAILED"),
            traces=trace_responses
        )


# ============================================================
# PAGINATION SCHEMAS
# ============================================================

class PaginationMeta(BaseModel):
    """Pagination metadata."""
    skip: int = 0
    limit: int = 100
    total: int = 0
    has_more: bool = False


class ExecutionListResponse(BaseModel):
    """Paginated execution list response."""
    items: List[ExecutionResponse]
    meta: PaginationMeta