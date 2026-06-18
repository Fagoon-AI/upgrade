"""
Unit tests for execution functionality.

Tests cover:
- WorkflowExecution model operations
- NodeExecutionTrace operations
- Execution status management
- Execution properties
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from src.models.sql.workflow.workflow import Workflow
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.schedule import WorkflowSchedule
from src.models.sql.workflow.user import User
from src.models.sql.workflow.connection import Connection
from src.models.sql.workflow.execution import (
    WorkflowExecution,
    ExecutionStatus,
    NodeExecutionTrace,
    TERMINAL_STATES,
)
from tests.factories.execution import (
    WorkflowExecutionFactory,
    NodeExecutionTraceFactory,
)


class TestExecutionModel:
    """Tests for WorkflowExecution model."""

    def test_execution_creation(self):
        """Execution should be created with default values."""
        workflow_id = uuid4()
        execution = WorkflowExecution(
            workflow_id=workflow_id,
        )

        assert execution.workflow_id == workflow_id
        assert execution.status == ExecutionStatus.PENDING
        assert execution.trigger_type == "MANUAL"
        assert execution.context_data == {}
        assert execution.results == {}

    def test_execution_is_terminal_for_completed(self):
        """Completed execution should be terminal."""
        execution = WorkflowExecutionFactory.create_completed()

        assert execution.is_terminal is True
        assert execution.status in TERMINAL_STATES

    def test_execution_is_terminal_for_failed(self):
        """Failed execution should be terminal."""
        execution = WorkflowExecutionFactory.create_failed()

        assert execution.is_terminal is True

    def test_execution_is_terminal_for_running(self):
        """Running execution should not be terminal."""
        execution = WorkflowExecutionFactory.create_running()

        assert execution.is_terminal is False

    def test_execution_is_terminal_for_paused(self):
        """Paused execution should not be terminal."""
        execution = WorkflowExecutionFactory.create_paused()

        assert execution.is_terminal is False

    def test_execution_is_running(self):
        """Running execution check."""
        running = WorkflowExecutionFactory.create_running()
        pending = WorkflowExecutionFactory.create_pending()

        assert running.is_running is True
        assert pending.is_running is False

    def test_execution_is_success(self):
        """Success check should only be true for completed."""
        completed = WorkflowExecutionFactory.create_completed()
        failed = WorkflowExecutionFactory.create_failed()

        assert completed.is_success is True
        assert failed.is_success is False


class TestExecutionStatusMethods:
    """Tests for execution status change methods."""

    def test_mark_running(self):
        """mark_running should update status and timestamp."""
        execution = WorkflowExecutionFactory.create_pending()
        original_started = execution.started_at

        execution.mark_running()

        assert execution.status == ExecutionStatus.RUNNING
        assert execution.started_at >= original_started

    def test_mark_completed(self):
        """mark_completed should set status and results."""
        execution = WorkflowExecutionFactory.create_running()
        results = {"output": "test_result"}

        execution.mark_completed(results=results)

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.finished_at is not None
        assert execution.results == results

    def test_mark_failed(self):
        """mark_failed should set error in context."""
        execution = WorkflowExecutionFactory.create_running()
        error = "Something went wrong"

        execution.mark_failed(error)

        assert execution.status == ExecutionStatus.FAILED
        assert execution.finished_at is not None
        assert execution.context_data.get("error") == error
        assert execution.error_message == error

    def test_mark_paused(self):
        """mark_paused should set pause reason."""
        execution = WorkflowExecutionFactory.create_running()
        reason = "Waiting for approval"

        execution.mark_paused(reason)

        assert execution.status == ExecutionStatus.PAUSED
        assert execution.context_data.get("pause_reason") == reason


class TestExecutionNodeOutput:
    """Tests for node output management."""

    def test_set_node_output(self):
        """Should store node output."""
        execution = WorkflowExecutionFactory()

        execution.set_node_output("node-1", {"result": 42})

        assert execution.context_data.get("node-1") == {"result": 42}

    def test_get_node_output(self):
        """Should retrieve node output."""
        execution = WorkflowExecutionFactory()
        execution.context_data = {"node-1": {"result": 42}}

        output = execution.get_node_output("node-1")

        assert output == {"result": 42}

    def test_get_node_output_not_found(self):
        """Should return None for missing node."""
        execution = WorkflowExecutionFactory()

        output = execution.get_node_output("non-existent")

        assert output is None

    def test_set_multiple_outputs(self):
        """Should store multiple node outputs."""
        execution = WorkflowExecutionFactory()

        execution.set_node_output("node-1", {"a": 1})
        execution.set_node_output("node-2", {"b": 2})

        assert execution.get_node_output("node-1") == {"a": 1}
        assert execution.get_node_output("node-2") == {"b": 2}


class TestExecutionDuration:
    """Tests for execution duration calculation."""

    def test_duration_for_completed(self):
        """Duration should be calculated for completed execution."""
        execution = WorkflowExecution(
            workflow_id=uuid4(),
            started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
            finished_at=datetime.now(timezone.utc),
            status=ExecutionStatus.COMPLETED,
        )

        assert execution.duration_ms is not None
        assert 4900 <= execution.duration_ms <= 5100  # ~5 seconds

    def test_duration_for_running(self):
        """Duration should be calculated from now for running."""
        execution = WorkflowExecution(
            workflow_id=uuid4(),
            started_at=datetime.now(timezone.utc) - timedelta(seconds=2),
            status=ExecutionStatus.RUNNING,
        )

        assert execution.duration_ms is not None
        assert execution.duration_ms >= 2000  # At least 2 seconds


class TestNodeExecutionTrace:
    """Tests for NodeExecutionTrace model."""

    def test_trace_creation(self):
        """Trace should be created with required fields."""
        trace = NodeExecutionTrace(
            execution_id=uuid4(),
            node_id="test-node",
            node_type="codeNode",
            status="SUCCESS",
        )

        assert trace.node_id == "test-node"
        assert trace.node_type == "codeNode"
        assert trace.status == "SUCCESS"
        assert trace.attempt_number == 1

    def test_trace_is_success(self):
        """is_success should reflect status."""
        success = NodeExecutionTraceFactory.create_success()
        failed = NodeExecutionTraceFactory.create_failed()

        assert success.is_success is True
        assert failed.is_success is False

    def test_trace_is_retry(self):
        """is_retry should be true for attempts > 1."""
        first = NodeExecutionTraceFactory(attempt_number=1)
        retry = NodeExecutionTraceFactory.create_retry(attempt=2)

        assert first.is_retry is False
        assert retry.is_retry is True


class TestExecutionFactory:
    """Tests for WorkflowExecutionFactory."""

    def test_create_pending(self):
        """Factory creates pending execution."""
        execution = WorkflowExecutionFactory.create_pending()

        assert execution.status == ExecutionStatus.PENDING

    def test_create_running(self):
        """Factory creates running execution."""
        execution = WorkflowExecutionFactory.create_running()

        assert execution.status == ExecutionStatus.RUNNING

    def test_create_completed(self):
        """Factory creates completed execution with results."""
        execution = WorkflowExecutionFactory.create_completed(
            results={"test": "value"}
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.finished_at is not None
        assert "test" in execution.results

    def test_create_failed(self):
        """Factory creates failed execution with error."""
        execution = WorkflowExecutionFactory.create_failed(
            error="Custom error message"
        )

        assert execution.status == ExecutionStatus.FAILED
        assert "Custom error message" in str(execution.context_data)

    def test_create_with_webhook_trigger(self):
        """Factory creates webhook-triggered execution."""
        execution = WorkflowExecutionFactory.create_with_webhook_trigger(
            webhook_id="wh-123"
        )

        assert execution.trigger_type == "WEBHOOK"
        assert "webhook_wh-123" in execution.external_event_id

    def test_create_batch(self):
        """Factory creates multiple executions."""
        workflow_id = uuid4()
        executions = WorkflowExecutionFactory.create_batch(
            workflow_id=workflow_id,
            count=5,
        )

        assert len(executions) == 5
        assert all(e.workflow_id == workflow_id for e in executions)


class TestNodeTraceFactory:
    """Tests for NodeExecutionTraceFactory."""

    def test_create_success_trace(self):
        """Factory creates successful trace."""
        trace = NodeExecutionTraceFactory.create_success()

        assert trace.status == "SUCCESS"
        assert trace.error_message is None

    def test_create_failed_trace(self):
        """Factory creates failed trace with error."""
        trace = NodeExecutionTraceFactory.create_failed(
            error_message="Node failed"
        )

        assert trace.status == "FAILED"
        assert trace.error_message == "Node failed"

    def test_create_skipped_trace(self):
        """Factory creates skipped trace."""
        trace = NodeExecutionTraceFactory.create_skipped()

        assert trace.status == "SKIPPED"
        assert trace.duration_ms == 0

    def test_create_for_node_type(self):
        """Factory creates trace for specific node type."""
        trace = NodeExecutionTraceFactory.create_for_node_type("agentNode")

        assert trace.node_type == "agentNode"
        assert "provider" in trace.inputs

    def test_create_workflow_traces(self):
        """Factory creates traces for entire workflow."""
        execution_id = uuid4()
        traces = NodeExecutionTraceFactory.create_workflow_traces(
            execution_id=execution_id,
            node_ids=["start-1", "code-1", "end-1"],
            node_types=["startNode", "codeNode", "endNode"],
        )

        assert len(traces) == 3
        assert all(t.execution_id == execution_id for t in traces)
        assert [t.node_type for t in traces] == ["startNode", "codeNode", "endNode"]


class TestExecutionSerialization:
    """Tests for execution serialization."""

    def test_to_dict_basic(self):
        """to_dict should include basic fields."""
        execution = WorkflowExecutionFactory.create_completed()

        data = execution.to_dict()

        assert "id" in data
        assert "workflow_id" in data
        assert "status" in data
        assert "duration_ms" in data

    def test_to_dict_includes_results_for_completed(self):
        """to_dict should include results for completed."""
        execution = WorkflowExecutionFactory.create_completed(
            results={"output": "value"}
        )

        data = execution.to_dict()

        assert "results" in data
        assert data["results"] == {"output": "value"}

    def test_to_dict_includes_error_for_failed(self):
        """to_dict should include error for failed."""
        execution = WorkflowExecutionFactory.create_failed(error="Test error")

        data = execution.to_dict()

        assert "error" in data
        assert data["error"] == "Test error"

    def test_to_dict_with_context(self):
        """to_dict can include full context."""
        execution = WorkflowExecutionFactory()
        execution.context_data = {"node-1": {"result": 42}}

        data = execution.to_dict(include_context=True)

        assert "context_data" in data
        assert "graph_snapshot" in data

    def test_to_dict_excludes_context_by_default(self):
        """to_dict should exclude context by default."""
        execution = WorkflowExecutionFactory()

        data = execution.to_dict()

        assert "context_data" not in data
