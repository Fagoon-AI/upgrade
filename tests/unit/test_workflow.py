"""
Unit tests for workflow functionality.

Tests cover:
- Workflow model operations
- Graph definition validation
- Status transitions
- Workflow properties
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from src.models.sql.workflow.workflow import Workflow, WorkflowStatus, STATUS_TRANSITIONS
from src.models.sql.workflow.version import WorkflowVersion
from src.models.sql.workflow.execution import WorkflowExecution
from src.models.sql.workflow.schedule import WorkflowSchedule
from src.models.sql.workflow.user import User
from src.models.sql.workflow.connection import Connection
from tests.factories.workflow import (
    WorkflowFactory,
    create_sample_graph,
    create_llm_workflow_graph,
    create_conditional_workflow_graph,
)


class TestWorkflowModel:
    """Tests for Workflow model."""

    def test_workflow_creation(self):
        """Workflow should be created with default values."""
        user_id = uuid4()
        workflow = Workflow(
            user_id=user_id,
            name="Test Workflow",
        )

        assert workflow.name == "Test Workflow"
        assert workflow.user_id == user_id
        assert workflow.status == WorkflowStatus.DRAFT
        assert workflow.version == 1
        assert workflow.graph_definition is not None

    def test_workflow_name_validation(self):
        """Workflow name should be sanitized via validator."""
        # Note: SQLModel validators run during model_validate, not direct __init__
        workflow = Workflow.model_validate({
            "user_id": str(uuid4()),
            "name": "  Test <script>alert('xss')</script> Workflow  ",
        })

        # Name should be trimmed and dangerous chars removed
        assert "<script>" not in workflow.name
        assert workflow.name.strip() == workflow.name

    def test_workflow_graph_validation(self):
        """Graph definition should have required keys via validator."""
        # Note: SQLModel validators run during model_validate, not direct __init__
        workflow = Workflow.model_validate({
            "user_id": str(uuid4()),
            "name": "Test",
            "graph_definition": None,  # Test None handling
        })

        # Should have default structure
        assert "nodes" in workflow.graph_definition
        assert "edges" in workflow.graph_definition
        assert "viewport" in workflow.graph_definition

    def test_workflow_node_count(self):
        """Node count should reflect graph definition."""
        graph = create_sample_graph(node_count=5)
        workflow = Workflow(
            user_id=uuid4(),
            name="Test",
            graph_definition=graph,
        )

        assert workflow.node_count == len(graph["nodes"])

    def test_workflow_edge_count(self):
        """Edge count should reflect graph definition."""
        graph = create_sample_graph()
        workflow = Workflow(
            user_id=uuid4(),
            name="Test",
            graph_definition=graph,
        )

        assert workflow.edge_count == len(graph["edges"])


class TestWorkflowStatusTransitions:
    """Tests for workflow status transitions."""

    def test_draft_to_published(self):
        """Draft workflow can be published."""
        workflow = WorkflowFactory.create_draft()

        assert workflow.can_transition_to(WorkflowStatus.PUBLISHED)
        workflow.transition_to(WorkflowStatus.PUBLISHED)
        assert workflow.status == WorkflowStatus.PUBLISHED

    def test_draft_to_archived(self):
        """Draft workflow can be archived."""
        workflow = WorkflowFactory.create_draft()

        assert workflow.can_transition_to(WorkflowStatus.ARCHIVED)
        workflow.transition_to(WorkflowStatus.ARCHIVED)
        assert workflow.status == WorkflowStatus.ARCHIVED

    def test_published_to_draft(self):
        """Published workflow can go back to draft."""
        workflow = WorkflowFactory.create_published()

        assert workflow.can_transition_to(WorkflowStatus.DRAFT)
        workflow.transition_to(WorkflowStatus.DRAFT)
        assert workflow.status == WorkflowStatus.DRAFT

    def test_published_to_disabled(self):
        """Published workflow can be disabled."""
        workflow = WorkflowFactory.create_published()

        assert workflow.can_transition_to(WorkflowStatus.DISABLED)
        workflow.transition_to(WorkflowStatus.DISABLED)
        assert workflow.status == WorkflowStatus.DISABLED

    def test_archived_to_draft(self):
        """Archived workflow can be restored to draft."""
        workflow = WorkflowFactory.create_archived()

        assert workflow.can_transition_to(WorkflowStatus.DRAFT)
        workflow.transition_to(WorkflowStatus.DRAFT)
        assert workflow.status == WorkflowStatus.DRAFT

    def test_invalid_transition(self):
        """Invalid transition should raise error."""
        workflow = WorkflowFactory.create_draft()

        # Draft cannot go directly to disabled
        assert not workflow.can_transition_to(WorkflowStatus.DISABLED)

        with pytest.raises(ValueError) as exc_info:
            workflow.transition_to(WorkflowStatus.DISABLED)

        assert "Cannot transition" in str(exc_info.value)

    def test_all_transitions_defined(self):
        """All statuses should have defined transitions."""
        for status in WorkflowStatus:
            assert status in STATUS_TRANSITIONS


class TestWorkflowRunnable:
    """Tests for workflow runnable check."""

    def test_published_with_version_is_runnable(self):
        """Published workflow with version and nodes is runnable."""
        workflow = WorkflowFactory.create_published()

        assert workflow.is_runnable is True

    def test_draft_not_runnable(self):
        """Draft workflow is not runnable."""
        workflow = WorkflowFactory.create_draft()

        assert workflow.is_runnable is False

    def test_published_without_version_not_runnable(self):
        """Published workflow without active version is not runnable."""
        workflow = WorkflowFactory(
            status=WorkflowStatus.PUBLISHED,
            active_version_id=None,  # No active version
        )

        assert workflow.is_runnable is False

    def test_published_empty_graph_not_runnable(self):
        """Published workflow with empty graph is not runnable."""
        workflow = WorkflowFactory.create_published()
        workflow.graph_definition = {"nodes": [], "edges": [], "viewport": {}}

        assert workflow.is_runnable is False


class TestWorkflowGraphOperations:
    """Tests for workflow graph operations."""

    def test_get_node_by_id(self):
        """Should find node by ID."""
        graph = create_sample_graph()
        workflow = Workflow(
            user_id=uuid4(),
            name="Test",
            graph_definition=graph,
        )

        node = workflow.get_node_by_id("start-1")

        assert node is not None
        assert node["id"] == "start-1"
        assert node["type"] == "startNode"

    def test_get_node_by_id_not_found(self):
        """Should return None for non-existent node."""
        workflow = WorkflowFactory()

        node = workflow.get_node_by_id("non-existent-node")

        assert node is None

    def test_get_start_node(self):
        """Should find start node."""
        workflow = WorkflowFactory()

        start = workflow.get_start_node()

        assert start is not None
        assert start["type"] == "startNode"

    def test_get_start_node_no_start(self):
        """Should return None if no start node."""
        workflow = Workflow(
            user_id=uuid4(),
            name="Test",
            graph_definition={
                "nodes": [{"id": "n1", "type": "codeNode", "data": {}}],
                "edges": [],
                "viewport": {},
            },
        )

        start = workflow.get_start_node()

        assert start is None


class TestWorkflowFactory:
    """Tests for WorkflowFactory."""

    def test_create_draft_workflow(self):
        """Factory should create draft workflow."""
        workflow = WorkflowFactory.create_draft()

        assert workflow.status == WorkflowStatus.DRAFT
        assert workflow.id is not None
        assert workflow.name is not None

    def test_create_published_workflow(self):
        """Factory should create published workflow with version."""
        workflow = WorkflowFactory.create_published()

        assert workflow.status == WorkflowStatus.PUBLISHED
        assert workflow.active_version_id is not None

    def test_create_with_llm_node(self):
        """Factory should create workflow with LLM node."""
        workflow = WorkflowFactory.create_with_llm_node()

        nodes = workflow.graph_definition.get("nodes", [])
        node_types = [n["type"] for n in nodes]

        assert "agentNode" in node_types

    def test_create_with_conditional(self):
        """Factory should create workflow with conditional branching."""
        workflow = WorkflowFactory.create_with_conditional()

        nodes = workflow.graph_definition.get("nodes", [])
        node_types = [n["type"] for n in nodes]

        assert "conditionNode" in node_types

    def test_create_empty_workflow(self):
        """Factory should create workflow with empty graph."""
        workflow = WorkflowFactory.create_empty()

        assert workflow.node_count == 0
        assert workflow.edge_count == 0


class TestWorkflowSerialization:
    """Tests for workflow serialization."""

    def test_to_dict_includes_graph(self):
        """to_dict should include graph by default."""
        workflow = WorkflowFactory()

        data = workflow.to_dict()

        assert "graph_definition" in data
        assert "global_variables" in data

    def test_to_dict_excludes_graph(self):
        """to_dict can exclude graph for listings."""
        workflow = WorkflowFactory()

        data = workflow.to_dict(include_graph=False)

        assert "graph_definition" not in data
        assert "global_variables" not in data

    def test_to_dict_includes_computed_fields(self):
        """to_dict should include computed fields."""
        workflow = WorkflowFactory.create_published()

        data = workflow.to_dict()

        assert "node_count" in data
        assert "edge_count" in data
        assert "is_runnable" in data

    def test_to_dict_id_as_string(self):
        """to_dict should convert UUIDs to strings."""
        workflow = WorkflowFactory()

        data = workflow.to_dict()

        assert isinstance(data["id"], str)
        assert isinstance(data["user_id"], str)
