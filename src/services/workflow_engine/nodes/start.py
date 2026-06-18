from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext

class StartNode(BaseNode):
    """
    Entry Point.
    Standardizes initial payload mapping for downstream Jinja2 hydration.
    """
    node_type = "startNode"

    @classmethod
    def get_manifest(cls):
        return {
            "type": cls.node_type,
            "display_name": "Start",
            "icon": "Play",
            "category": "Logic & Flow",
            "description": "The entry point of your workflow.",
            "fields": [],
            "outputs": ["status", "initial_input"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status ('started')"},
                "initial_input": {"type": "object", "description": "The initial payload passed to the workflow"}
            }
        }

    async def execute(self, db: AsyncSession, context: ExecutionContext, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "started",
            "initial_input": input_data.get("initial_input", input_data)
        }