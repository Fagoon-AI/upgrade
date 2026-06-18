"""
Workflow model factory for test data generation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import factory
from faker import Faker

from src.models.sql.workflow.workflow import Workflow, WorkflowStatus

fake = Faker()


def create_sample_graph(
    node_count: int = 3,
    include_code_node: bool = True,
) -> Dict[str, Any]:
    """
    Create a sample workflow graph definition.

    Args:
        node_count: Number of nodes (minimum 2 for start/end)
        include_code_node: Whether to include a code node

    Returns:
        Graph definition dictionary
    """
    nodes = [
        {
            "id": "start-1",
            "type": "startNode",
            "position": {"x": 100, "y": 100},
            "data": {"label": "Start", "triggerType": "manual"},
        }
    ]

    edges = []
    prev_node_id = "start-1"

    if include_code_node and node_count >= 3:
        code_node = {
            "id": "code-1",
            "type": "codeNode",
            "position": {"x": 300, "y": 100},
            "data": {
                "label": "Process Data",
                "code": "result = input_data.get('value', 0) * 2\noutput = {'result': result}",
                "language": "python",
            },
        }
        nodes.append(code_node)
        edges.append({
            "id": f"e-{prev_node_id}-code-1",
            "source": prev_node_id,
            "target": "code-1",
        })
        prev_node_id = "code-1"

    # Add end node
    end_node = {
        "id": "end-1",
        "type": "endNode",
        "position": {"x": 500, "y": 100},
        "data": {"label": "End"},
    }
    nodes.append(end_node)
    edges.append({
        "id": f"e-{prev_node_id}-end-1",
        "source": prev_node_id,
        "target": "end-1",
    })

    return {
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def create_llm_workflow_graph() -> Dict[str, Any]:
    """Create a workflow graph with LLM node."""
    return {
        "nodes": [
            {
                "id": "start-1",
                "type": "startNode",
                "position": {"x": 100, "y": 100},
                "data": {"label": "Start"},
            },
            {
                "id": "llm-1",
                "type": "agentNode",
                "position": {"x": 300, "y": 100},
                "data": {
                    "label": "AI Agent",
                    "provider": "openai",
                    "model": "gpt-4",
                    "prompt": "Process the following: {{input}}",
                    "temperature": 0.7,
                },
            },
            {
                "id": "end-1",
                "type": "endNode",
                "position": {"x": 500, "y": 100},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start-1", "target": "llm-1"},
            {"id": "e2", "source": "llm-1", "target": "end-1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def create_conditional_workflow_graph() -> Dict[str, Any]:
    """Create a workflow graph with conditional branching."""
    return {
        "nodes": [
            {
                "id": "start-1",
                "type": "startNode",
                "position": {"x": 100, "y": 200},
                "data": {"label": "Start"},
            },
            {
                "id": "condition-1",
                "type": "conditionNode",
                "position": {"x": 300, "y": 200},
                "data": {
                    "label": "Check Value",
                    "condition": "input_data.get('value', 0) > 10",
                },
            },
            {
                "id": "code-true",
                "type": "codeNode",
                "position": {"x": 500, "y": 100},
                "data": {"label": "High Value", "code": "output = 'high'"},
            },
            {
                "id": "code-false",
                "type": "codeNode",
                "position": {"x": 500, "y": 300},
                "data": {"label": "Low Value", "code": "output = 'low'"},
            },
            {
                "id": "end-1",
                "type": "endNode",
                "position": {"x": 700, "y": 200},
                "data": {"label": "End"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start-1", "target": "condition-1"},
            {
                "id": "e2",
                "source": "condition-1",
                "target": "code-true",
                "data": {"condition": "true"},
            },
            {
                "id": "e3",
                "source": "condition-1",
                "target": "code-false",
                "data": {"condition": "false"},
            },
            {"id": "e4", "source": "code-true", "target": "end-1"},
            {"id": "e5", "source": "code-false", "target": "end-1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


class WorkflowFactory(factory.Factory):
    """
    Factory for creating Workflow instances.

    Usage:
        # Create draft workflow
        workflow = WorkflowFactory()

        # Create published workflow
        workflow = WorkflowFactory.create_published(user_id=user.id)

        # Create with specific graph
        workflow = WorkflowFactory(graph_definition=custom_graph)
    """

    class Meta:
        model = Workflow

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    user_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    name: str = factory.LazyFunction(lambda: f"Workflow {fake.word().title()}")
    description: Optional[str] = factory.LazyFunction(fake.sentence)
    graph_definition: Dict[str, Any] = factory.LazyFunction(create_sample_graph)
    status: WorkflowStatus = WorkflowStatus.DRAFT
    version: int = 1
    active_version_id: Optional[uuid.UUID] = None
    global_variables: Dict[str, Any] = factory.LazyFunction(dict)
    created_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at: datetime = factory.LazyFunction(lambda: datetime.now(timezone.utc))

    @classmethod
    def create_draft(cls, **kwargs) -> Workflow:
        """Create a draft workflow."""
        return cls(status=WorkflowStatus.DRAFT, **kwargs)

    @classmethod
    def create_published(cls, **kwargs) -> Workflow:
        """Create a published workflow ready for execution."""
        return cls(
            status=WorkflowStatus.PUBLISHED,
            active_version_id=uuid.uuid4(),
            **kwargs,
        )

    @classmethod
    def create_archived(cls, **kwargs) -> Workflow:
        """Create an archived workflow."""
        return cls(status=WorkflowStatus.ARCHIVED, **kwargs)

    @classmethod
    def create_disabled(cls, **kwargs) -> Workflow:
        """Create a disabled workflow."""
        return cls(status=WorkflowStatus.DISABLED, **kwargs)

    @classmethod
    def create_with_llm_node(cls, **kwargs) -> Workflow:
        """Create workflow with LLM/Agent node."""
        return cls(graph_definition=create_llm_workflow_graph(), **kwargs)

    @classmethod
    def create_with_conditional(cls, **kwargs) -> Workflow:
        """Create workflow with conditional branching."""
        return cls(graph_definition=create_conditional_workflow_graph(), **kwargs)

    @classmethod
    def create_empty(cls, **kwargs) -> Workflow:
        """Create workflow with empty graph."""
        return cls(
            graph_definition={"nodes": [], "edges": [], "viewport": {}},
            **kwargs,
        )


class WorkflowCreateDataFactory(factory.Factory):
    """Factory for workflow creation request data."""

    class Meta:
        model = dict

    name: str = factory.LazyFunction(lambda: f"New Workflow {fake.word()}")
    description: str = factory.LazyFunction(fake.sentence)
    graph_definition: Dict[str, Any] = factory.LazyFunction(create_sample_graph)

    @classmethod
    def minimal(cls) -> dict:
        """Create minimal workflow data (name only)."""
        return {"name": f"Minimal Workflow {fake.word()}"}

    @classmethod
    def with_empty_name(cls) -> dict:
        """Create workflow data with empty name (for validation tests)."""
        data = cls()
        data["name"] = ""
        return data
