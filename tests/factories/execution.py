"""
Execution model factories for test data generation.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import factory
from faker import Faker

from src.models.sql.workflow.execution import (
    WorkflowExecution,
    ExecutionStatus,
    NodeExecutionTrace,
    TERMINAL_STATES,
)

fake = Faker()


class WorkflowExecutionFactory(factory.Factory):
    """
    Factory for creating WorkflowExecution instances.

    Usage:
        # Create pending execution
        execution = WorkflowExecutionFactory()

        # Create completed execution
        execution = WorkflowExecutionFactory.create_completed(workflow_id=wf.id)

        # Create failed execution
        execution = WorkflowExecutionFactory.create_failed(
            workflow_id=wf.id,
            error="Something went wrong"
        )
    """

    class Meta:
        model = WorkflowExecution

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    workflow_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    version_id: Optional[uuid.UUID] = factory.LazyFunction(uuid.uuid4)
    trigger_type: str = "MANUAL"
    status: ExecutionStatus = ExecutionStatus.PENDING
    graph_snapshot: Dict[str, Any] = factory.LazyFunction(
        lambda: {
            "nodes": [
                {"id": "start-1", "type": "startNode", "data": {}},
                {"id": "end-1", "type": "endNode", "data": {}},
            ],
            "edges": [{"id": "e1", "source": "start-1", "target": "end-1"}],
        }
    )
    context_data: Dict[str, Any] = factory.LazyFunction(dict)
    results: Dict[str, Any] = factory.LazyFunction(dict)
    external_event_id: Optional[str] = None
    started_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @classmethod
    def create_pending(cls, **kwargs) -> WorkflowExecution:
        """Create a pending execution."""
        return cls(status=ExecutionStatus.PENDING, **kwargs)

    @classmethod
    def create_running(cls, **kwargs) -> WorkflowExecution:
        """Create a running execution."""
        return cls(status=ExecutionStatus.RUNNING, **kwargs)

    @classmethod
    def create_completed(cls, results: Optional[dict] = None, **kwargs) -> WorkflowExecution:
        """
        Create a completed execution.

        Args:
            results: Execution results
            **kwargs: Additional fields
        """
        return cls(
            status=ExecutionStatus.COMPLETED,
            finished_at=datetime.now(timezone.utc),
            results=results or {"success": True, "output": "completed"},
            context_data={"start-1": {}, "end-1": {}},
            **kwargs,
        )

    @classmethod
    def create_failed(cls, error: str = "Execution failed", **kwargs) -> WorkflowExecution:
        """
        Create a failed execution.

        Args:
            error: Error message
            **kwargs: Additional fields
        """
        return cls(
            status=ExecutionStatus.FAILED,
            finished_at=datetime.now(timezone.utc),
            context_data={"error": error},
            **kwargs,
        )

    @classmethod
    def create_paused(cls, reason: str = "Awaiting approval", **kwargs) -> WorkflowExecution:
        """Create a paused execution (HITL)."""
        return cls(
            status=ExecutionStatus.PAUSED,
            context_data={"pause_reason": reason, "paused_at_node": "approval-1"},
            **kwargs,
        )

    @classmethod
    def create_cancelled(cls, **kwargs) -> WorkflowExecution:
        """Create a cancelled execution."""
        return cls(
            status=ExecutionStatus.CANCELLED,
            finished_at=datetime.now(timezone.utc),
            **kwargs,
        )

    @classmethod
    def create_timeout(cls, **kwargs) -> WorkflowExecution:
        """Create a timed-out execution."""
        return cls(
            status=ExecutionStatus.TIMEOUT,
            finished_at=datetime.now(timezone.utc),
            context_data={"error": "Execution timed out"},
            **kwargs,
        )

    @classmethod
    def create_with_webhook_trigger(cls, webhook_id: str, **kwargs) -> WorkflowExecution:
        """Create execution triggered by webhook."""
        return cls(
            trigger_type="WEBHOOK",
            external_event_id=f"webhook_{webhook_id}_{uuid.uuid4().hex[:8]}",
            **kwargs,
        )

    @classmethod
    def create_with_schedule_trigger(cls, schedule_id: str, **kwargs) -> WorkflowExecution:
        """Create execution triggered by schedule."""
        return cls(
            trigger_type="SCHEDULE",
            external_event_id=f"schedule_{schedule_id}_{uuid.uuid4().hex[:8]}",
            **kwargs,
        )

    @classmethod
    def create_batch(
        cls,
        workflow_id: uuid.UUID,
        count: int,
        status: Optional[ExecutionStatus] = None,
    ) -> list[WorkflowExecution]:
        """
        Create multiple executions for a workflow.

        Args:
            workflow_id: Parent workflow ID
            count: Number of executions
            status: Optional status for all executions

        Returns:
            List of WorkflowExecution instances
        """
        kwargs = {"workflow_id": workflow_id}
        if status:
            kwargs["status"] = status
        return [cls(**kwargs) for _ in range(count)]


class NodeExecutionTraceFactory(factory.Factory):
    """
    Factory for creating NodeExecutionTrace instances.

    Usage:
        # Create successful trace
        trace = NodeExecutionTraceFactory()

        # Create failed trace
        trace = NodeExecutionTraceFactory.create_failed(
            execution_id=exec.id,
            error_message="Node failed"
        )
    """

    class Meta:
        model = NodeExecutionTrace

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    execution_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    node_id: str = factory.LazyFunction(lambda: f"node-{fake.uuid4()[:8]}")
    node_type: str = "codeNode"
    inputs: Dict[str, Any] = factory.LazyFunction(lambda: {"input": fake.word()})
    outputs: Dict[str, Any] = factory.LazyFunction(lambda: {"output": fake.word()})
    status: str = "SUCCESS"
    error_message: Optional[str] = None
    duration_ms: int = factory.LazyFunction(lambda: fake.random_int(min=10, max=5000))
    attempt_number: int = 1
    created_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    def create_success(cls, **kwargs) -> NodeExecutionTrace:
        """Create a successful trace."""
        return cls(status="SUCCESS", **kwargs)

    @classmethod
    def create_failed(
        cls,
        error_message: str = "Node execution failed",
        **kwargs,
    ) -> NodeExecutionTrace:
        """Create a failed trace."""
        return cls(
            status="FAILED",
            error_message=error_message,
            outputs={},
            **kwargs,
        )

    @classmethod
    def create_skipped(cls, **kwargs) -> NodeExecutionTrace:
        """Create a skipped trace (conditional branch not taken)."""
        return cls(
            status="SKIPPED",
            duration_ms=0,
            inputs={},
            outputs={},
            **kwargs,
        )

    @classmethod
    def create_retry(cls, attempt: int = 2, **kwargs) -> NodeExecutionTrace:
        """Create a retry trace."""
        return cls(attempt_number=attempt, **kwargs)

    @classmethod
    def create_for_node_type(cls, node_type: str, **kwargs) -> NodeExecutionTrace:
        """
        Create trace for specific node type.

        Supported types: startNode, endNode, codeNode, agentNode,
        conditionNode, gmailNode, webhookNode
        """
        node_configs = {
            "startNode": {"inputs": {"trigger": "manual"}, "outputs": {"started": True}},
            "endNode": {"inputs": {"result": "done"}, "outputs": {}},
            "codeNode": {"inputs": {"code": "x = 1"}, "outputs": {"result": 1}},
            "agentNode": {
                "inputs": {"prompt": "Hello", "provider": "openai"},
                "outputs": {"response": "Hi there!", "tokens": 50},
            },
            "conditionNode": {
                "inputs": {"condition": "x > 5"},
                "outputs": {"branch": "true"},
            },
            "gmailNode": {
                "inputs": {"to": "test@example.com", "subject": "Test"},
                "outputs": {"message_id": "abc123"},
            },
        }

        config = node_configs.get(node_type, {})
        return cls(node_type=node_type, **config, **kwargs)

    @classmethod
    def create_workflow_traces(
        cls,
        execution_id: uuid.UUID,
        node_ids: list[str],
        node_types: Optional[list[str]] = None,
    ) -> list[NodeExecutionTrace]:
        """
        Create traces for an entire workflow execution.

        Args:
            execution_id: Parent execution ID
            node_ids: List of node IDs
            node_types: Optional list of node types (defaults to codeNode)

        Returns:
            List of NodeExecutionTrace instances
        """
        if node_types is None:
            node_types = ["codeNode"] * len(node_ids)

        traces = []
        base_time = datetime.now(timezone.utc)

        for i, (node_id, node_type) in enumerate(zip(node_ids, node_types)):
            trace = cls(
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                created_at=base_time + timedelta(milliseconds=i * 100),
            )
            traces.append(trace)

        return traces
