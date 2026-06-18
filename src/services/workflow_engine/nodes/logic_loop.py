import json
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import BaseLoader
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class LoopConfig:
    """Configuration for loop operations."""
    max_items: int = 10_000  # Maximum items to process
    default_batch_size: int = 100
    max_batch_size: int = 1_000
    default_concurrency: int = 5
    max_concurrency: int = 50


# ============================================================
# LOOP NODE
# ============================================================

class LoopNode(BaseNode):
    """
    Loop/Iterator Node.

    Features:
    - Sequential and parallel execution
    - Configurable concurrency
    - Batch processing
    - Break/continue conditions
    - Item transformation
    - Error handling modes
    - Progress tracking

    Outputs:
    - items: The items to iterate over
    - items_count: Number of items
    - batch_count: Number of batches (if batching enabled)
    - selected_branch: 'start' if items exist, 'completed' if empty

    Execution Modes:
    - Sequential: Process one item at a time
    - Parallel: Process multiple items concurrently
    - Batched: Group items into batches for processing
    """

    node_type = "loopNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Loop",
            "icon": "Repeat",
            "category": "Logic & Flow",
            "description": "Iterate over a list of items sequentially or in parallel.",
            "fields": [
                {
                    "name": "items",
                    "label": "Items to Iterate",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "{{ steps['api'].results }}",
                    "helper": "List of items or Jinja2 expression"
                },
                {
                    "name": "parallel",
                    "label": "Parallel Execution",
                    "type": "boolean",
                    "default": False,
                    "helper": "Process items concurrently"
                },
                {
                    "name": "max_concurrency",
                    "label": "Max Concurrency",
                    "type": "number",
                    "default": 5,
                    "min": 1,
                    "max": 50,
                    "conditional": {"parallel": True},
                    "helper": "Maximum parallel workers"
                },
                {
                    "name": "batch_size",
                    "label": "Batch Size",
                    "type": "number",
                    "default": 0,
                    "helper": "Group items into batches (0 = no batching)"
                },
                {
                    "name": "max_items",
                    "label": "Max Items",
                    "type": "number",
                    "default": 0,
                    "helper": "Limit items processed (0 = no limit)"
                },
                {
                    "name": "skip_items",
                    "label": "Skip Items",
                    "type": "number",
                    "default": 0,
                    "helper": "Skip first N items"
                },
                {
                    "name": "filter_expression",
                    "label": "Filter Expression",
                    "type": "textarea",
                    "placeholder": "{{ item.status == 'active' }}",
                    "helper": "Only include items where expression is true"
                },
                {
                    "name": "transform_expression",
                    "label": "Transform Expression",
                    "type": "textarea",
                    "placeholder": "{{ item.id }}",
                    "helper": "Transform each item before processing"
                },
                {
                    "name": "break_condition",
                    "label": "Break Condition",
                    "type": "textarea",
                    "placeholder": "{{ item.is_last == true }}",
                    "helper": "Stop iteration when condition is true"
                },
                {
                    "name": "error_handling",
                    "label": "Error Handling",
                    "type": "select",
                    "options": ["stop", "skip", "collect"],
                    "default": "stop",
                    "helper": "How to handle item errors"
                },
                {
                    "name": "empty_behavior",
                    "label": "Empty List Behavior",
                    "type": "select",
                    "options": ["completed", "error"],
                    "default": "completed",
                    "helper": "What to do when list is empty"
                }
            ],
            "outputs": ["status", "items", "items_count", "parallel", "max_concurrency", "selected_branch"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status ('success' or 'error')"},
                "items": {"type": "array", "description": "The items to iterate over"},
                "items_count": {"type": "number", "description": "Number of items to process"},
                "parallel": {"type": "boolean", "description": "Whether parallel execution is enabled"},
                "max_concurrency": {"type": "number", "description": "Maximum concurrent workers"},
                "selected_branch": {"type": "string", "description": "Branch taken: 'start', 'completed', or 'error'"}
            },
            "output_handles": [
                {"id": "start", "label": "Loop Body", "type": "any", "description": "Connect to nodes that process each item"},
                {"id": "completed", "label": "Completed", "type": "any", "description": "Taken when all items are processed or list is empty"},
                {"id": "error", "label": "Error", "type": "any", "description": "Taken when an error occurs"}
            ]
        }

    def __init__(self):
        super().__init__()
        self.config = LoopConfig()
        self.jinja = SandboxedEnvironment(loader=BaseLoader())

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes loop initialization."""
        # Get and parse items
        items = self._get_items(input_data, context)

        if items is None:
            return {
                "status": "error",
                "error": "Failed to parse items",
                "selected_branch": "error"
            }

        # Handle empty list
        if not items:
            empty_behavior = input_data.get("empty_behavior", "completed")

            if empty_behavior == "error":
                return {
                    "status": "error",
                    "error": "Input list is empty",
                    "selected_branch": "error"
                }

            return {
                "status": "success",
                "items": [],
                "items_count": 0,
                "message": "No items to process",
                "selected_branch": "completed"
            }

        # Apply skip
        skip = max(0, int(input_data.get("skip_items", 0)))
        if skip > 0:
            items = items[skip:]

        # Apply max items limit
        max_items = input_data.get("max_items", 0)
        if max_items and max_items > 0:
            items = items[:max_items]

        # Apply global safety limit
        if len(items) > self.config.max_items:
            logger.warning(f"Items truncated from {len(items)} to {self.config.max_items}")
            items = items[:self.config.max_items]

        # Apply filter
        filter_expr = input_data.get("filter_expression", "").strip()
        if filter_expr:
            items = self._filter_items(items, filter_expr, context)

        # Apply transformation
        transform_expr = input_data.get("transform_expression", "").strip()
        if transform_expr:
            items = self._transform_items(items, transform_expr, context)

        # Get execution options
        is_parallel = input_data.get("parallel", False)
        max_concurrency = min(
            int(input_data.get("max_concurrency", self.config.default_concurrency)),
            self.config.max_concurrency
        )

        # Handle batching
        batch_size = int(input_data.get("batch_size", 0))
        batches = None

        if batch_size > 0:
            batch_size = min(batch_size, self.config.max_batch_size)
            batches = self._create_batches(items, batch_size)

        # Build response
        response = {
            "status": "success",
            "items": items,
            "items_count": len(items),
            "parallel": is_parallel,
            "max_concurrency": max_concurrency,
            "error_handling": input_data.get("error_handling", "stop"),
            "break_condition": input_data.get("break_condition", ""),
            "selected_branch": "start"
        }

        if batches:
            response["batches"] = batches
            response["batch_count"] = len(batches)
            response["batch_size"] = batch_size

        return response

    def _get_items(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Optional[List[Any]]:
        """Extracts and parses items from input."""
        items_input = input_data.get("items")

        if items_input is None:
            return []

        # Already a list
        if isinstance(items_input, list):
            return items_input

        # Dict - convert to list of values or items
        if isinstance(items_input, dict):
            return list(items_input.values())

        # String - try to parse
        if isinstance(items_input, str):
            items_input = items_input.strip()

            # Try JSON array
            if items_input.startswith('['):
                try:
                    parsed = json.loads(items_input)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass

            # Try JSON object (convert to list)
            if items_input.startswith('{'):
                try:
                    parsed = json.loads(items_input)
                    if isinstance(parsed, dict):
                        return list(parsed.values())
                except json.JSONDecodeError:
                    pass

            # Split by common delimiters
            if ',' in items_input:
                return [i.strip() for i in items_input.split(',') if i.strip()]

            if '\n' in items_input:
                return [i.strip() for i in items_input.split('\n') if i.strip()]

            # Single item
            return [items_input] if items_input else []

        # Tuple or set
        if isinstance(items_input, (tuple, set)):
            return list(items_input)

        # Single item
        return [items_input]

    def _filter_items(
            self,
            items: List[Any],
            expression: str,
            context: ExecutionContext
    ) -> List[Any]:
        """Filters items based on Jinja2 expression."""
        filtered = []

        for item in items:
            try:
                template = self.jinja.from_string(expression)
                result = template.render(
                    item=item,
                    steps=context.node_outputs,
                    index=len(filtered)
                )

                # Check if truthy
                result = result.strip().lower()
                if result in ('true', '1', 'yes', 'y'):
                    filtered.append(item)
                elif result and result not in ('false', '0', 'no', 'n', ''):
                    filtered.append(item)

            except Exception as e:
                logger.debug(f"Filter expression error for item: {e}")
                # Include item on error (fail open)
                filtered.append(item)

        return filtered

    def _transform_items(
            self,
            items: List[Any],
            expression: str,
            context: ExecutionContext
    ) -> List[Any]:
        """Transforms items using Jinja2 expression."""
        transformed = []

        for idx, item in enumerate(items):
            try:
                template = self.jinja.from_string(expression)
                result = template.render(
                    item=item,
                    steps=context.node_outputs,
                    index=idx
                )

                # Try to parse JSON result
                result = result.strip()
                try:
                    transformed.append(json.loads(result))
                except json.JSONDecodeError:
                    transformed.append(result)

            except Exception as e:
                logger.debug(f"Transform expression error for item: {e}")
                # Keep original on error
                transformed.append(item)

        return transformed

    def _create_batches(
            self,
            items: List[Any],
            batch_size: int
    ) -> List[List[Any]]:
        """Creates batches from items."""
        batches = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batches.append(batch)

        return batches