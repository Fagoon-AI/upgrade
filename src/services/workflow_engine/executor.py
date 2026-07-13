import asyncio
import time
import random
import json
import copy
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Callable, Awaitable, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from contextlib import asynccontextmanager
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from jinja2 import Environment, BaseLoader, UndefinedError, TemplateSyntaxError, Undefined

from src.services.workflow_engine.context import ExecutionContext, ContextState, create_execution_context
from src.services.workflow_engine.registry import get_registry, NodeNotFoundError
from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError
from src.models.sql.workflow.execution import NodeExecutionTrace


# CIRCUIT BREAKER

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass
class CircuitBreaker:
    """Circuit breaker for preventing cascading failures."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3

    _failures: Dict[str, int] = field(default_factory=dict)
    _state: Dict[str, CircuitState] = field(default_factory=dict)
    _last_failure_time: Dict[str, float] = field(default_factory=dict)
    _half_open_calls: Dict[str, int] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def can_execute(self, node_type: str) -> bool:
        async with self._lock:
            state = self._state.get(node_type, CircuitState.CLOSED)

            if state == CircuitState.CLOSED:
                return True

            if state == CircuitState.OPEN:
                last_failure = self._last_failure_time.get(node_type, 0)
                if time.time() - last_failure > self.recovery_timeout:
                    self._state[node_type] = CircuitState.HALF_OPEN
                    self._half_open_calls[node_type] = 0
                    logger.info(f"Circuit half-open for {node_type}")
                    return True
                return False

            if state == CircuitState.HALF_OPEN:
                calls = self._half_open_calls.get(node_type, 0)
                if calls < self.half_open_max_calls:
                    self._half_open_calls[node_type] = calls + 1
                    return True
                return False

            return True

    async def record_success(self, node_type: str) -> None:
        async with self._lock:
            state = self._state.get(node_type, CircuitState.CLOSED)
            if state == CircuitState.HALF_OPEN:
                self._state[node_type] = CircuitState.CLOSED
                self._failures[node_type] = 0
                logger.info(f"Circuit closed for {node_type} (recovered)")
            elif state == CircuitState.CLOSED:
                self._failures[node_type] = 0

    async def record_failure(self, node_type: str) -> None:
        async with self._lock:
            failures = self._failures.get(node_type, 0) + 1
            self._failures[node_type] = failures
            self._last_failure_time[node_type] = time.time()

            state = self._state.get(node_type, CircuitState.CLOSED)

            if state == CircuitState.HALF_OPEN:
                self._state[node_type] = CircuitState.OPEN
                logger.warning(f"Circuit opened for {node_type} (recovery failed)")
            elif state == CircuitState.CLOSED and failures >= self.failure_threshold:
                self._state[node_type] = CircuitState.OPEN
                logger.warning(f"Circuit opened for {node_type} (threshold exceeded)")

    def get_status(self) -> Dict[str, Any]:
        return {
            node_type: {
                "state": self._state.get(node_type, CircuitState.CLOSED).name,
                "failures": self._failures.get(node_type, 0)
            }
            for node_type in set(self._state.keys()) | set(self._failures.keys())
        }


# INPUT RESOLVER

class SilentUndefined(Undefined):
    """Custom Undefined that returns empty string."""

    def _fail_with_undefined_error(self, *args, **kwargs):
        return ""

    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


class InputResolver:
    """
    Enhanced input resolver with:
    - Jinja2 template resolution
    - Node label alias support ({{ NodeLabel.field }})
    - @previous reference support
    """

    def __init__(self, nodes: Dict[str, Any] = None):
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=False,
            undefined=SilentUndefined
        )

        self.env.filters['default'] = lambda v, d: v if v else d
        self.env.filters['json_parse'] = self._safe_json_parse
        self.env.filters['int'] = self._safe_int
        self.env.filters['float'] = self._safe_float

        # Build alias map from nodes
        self._alias_map: Dict[str, str] = {}
        if nodes:
            self._build_alias_map(nodes)

    def _build_alias_map(self, nodes: Dict[str, Any]) -> None:
        """Builds mapping from node labels to node IDs."""
        for node_id, node_def in nodes.items():
            label = node_def.get("data", {}).get("label") or node_id
            label = str(label)
            # Clean label: remove spaces, make it a valid identifier
            clean_label = label.replace(" ", "").replace("-", "_")
            self._alias_map[clean_label] = node_id
            self._alias_map[label] = node_id  # Also support original label

    def _safe_json_parse(self, value: str) -> Any:
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            return value

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _resolve_aliases(self, template: str, execution_order: List[str] = None) -> str:
        """
        Resolves user-friendly aliases to full Jinja2 paths.

        Supports:
        - {{ NodeLabel.field }} -> {{ steps['node-id'].field }}
        - {{ @previous.field }} -> {{ steps['previous-node-id'].field }}
        """
        import re

        result = template

        # Replace @previous with actual previous node
        if "@previous" in template and execution_order:
            previous_node_id = execution_order[-1] if execution_order else None
            if previous_node_id:
                result = result.replace("@previous", f"steps['{previous_node_id}']")

        # Replace NodeLabel.field with steps['node-id'].field
        # Pattern: {{ NodeLabel.field }} where NodeLabel doesn't start with 'steps'
        pattern = r'\{\{\s*([A-Z][A-Za-z0-9_]*)\.([\w\.]+)\s*\}\}'

        def replace_alias(match):
            label = match.group(1)
            field = match.group(2)

            # Skip if it's already using steps syntax
            if label == "steps":
                return match.group(0)

            node_id = self._alias_map.get(label)
            if node_id:
                return f"{{{{ steps['{node_id}'].{field} }}}}"
            return match.group(0)  # Keep original if not found

        result = re.sub(pattern, replace_alias, result)

        return result

    def resolve(
            self,
            config: Dict[str, Any],
            context_data: Dict[str, Any],
            loop_item: Any = None,
            global_vars: Dict[str, Any] = None,
            execution_order: List[str] = None
    ) -> Dict[str, Any]:
        """Resolves Jinja2 templates in configuration."""
        template_context = {
            "steps": context_data,
            "item": loop_item,
            "env": global_vars or {}
        }

        def resolve_value(val: Any) -> Any:
            if isinstance(val, str) and "{{" in val and "}}" in val:
                try:
                    # First resolve aliases
                    resolved_template = self._resolve_aliases(val, execution_order)

                    template = self.env.from_string(resolved_template)
                    rendered = template.render(**template_context)

                    if rendered.strip().startswith(("{", "[")):
                        try:
                            return json.loads(rendered)
                        except json.JSONDecodeError:
                            pass

                    return rendered
                except (UndefinedError, TemplateSyntaxError) as e:
                    logger.warning(f"Template resolution failed: {e}")
                    return val
            elif isinstance(val, dict):
                return {k: resolve_value(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [resolve_value(item) for item in val]
            return val

        return resolve_value(config)


# EXECUTION TRACE (Enhanced with Cost Tracking)

@dataclass
class NodeTrace:
    """Records execution details with cost tracking."""
    node_id: str
    node_type: str
    status: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    duration_ms: int = 0
    attempt_number: int = 1
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "inputs": self._mask_secrets(self.inputs),
            "outputs": self._mask_secrets(self.outputs) if self.outputs else None,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": str(self.cost_usd)
            }
        }

    def _mask_secrets(self, data: Any) -> Any:
        SENSITIVE_KEYS = {
            "api_key", "secret", "password", "token", "access_token",
            "refresh_token", "private_key", "credentials"
        }

        if isinstance(data, dict):
            return {
                k: ("[REDACTED]" if any(sk in k.lower() for sk in SENSITIVE_KEYS)
                    else self._mask_secrets(v))
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._mask_secrets(item) for item in data]
        return data


# DATA MAPPING RESOLVER

class DataMappingResolver:
    """
    Resolves visual edge connections to actual data.

    Supports three entry points that all produce the same result:
    1. Visual Data Flow: User draws connections in UI
    2. Variable Picker: User clicks to insert variables
    3. Manual Jinja2: Developer writes templates directly

    Handles:
    - Single connections: Direct value pass
    - Multiple connections to same input: Merge strategies
    - Field extraction with dot notation
    - Data transformations with default values
    """

    # Merge strategies for multiple inputs to same handle
    MERGE_STRATEGIES = {
        "concatenate": lambda values: "\n\n---\n\n".join(str(v) for v in values if v),
        "array": lambda values: list(values),
        "merge_dict": lambda values: {k: v for d in values for k, v in (d.items() if isinstance(d, dict) else [])},
        "first": lambda values: values[0] if values else None,
        "last": lambda values: values[-1] if values else None,
    }

    # Available transforms - matches DataTransform enum in schemas
    TRANSFORMS = {
        "json": lambda v: json.loads(v) if isinstance(v, str) else v,
        "string": lambda v: str(v) if v is not None else "",
        "first_item": lambda v: v[0] if isinstance(v, list) and v else None,
        "last_item": lambda v: v[-1] if isinstance(v, list) and v else None,
        "join": lambda v: ", ".join(str(x) for x in v) if isinstance(v, list) else str(v),
        "count": lambda v: len(v) if isinstance(v, (list, dict, str)) else 0,
        "keys": lambda v: list(v.keys()) if isinstance(v, dict) else [],
        "values": lambda v: list(v.values()) if isinstance(v, dict) else [],
        "trim": lambda v: v.strip() if isinstance(v, str) else v,
        "lowercase": lambda v: v.lower() if isinstance(v, str) else v,
        "uppercase": lambda v: v.upper() if isinstance(v, str) else v,
        "flatten": lambda v: [item for sublist in v for item in (sublist if isinstance(sublist, list) else [sublist])] if isinstance(v, list) else v,
        "unique": lambda v: list(dict.fromkeys(v)) if isinstance(v, list) else v,
        "sort": lambda v: sorted(v) if isinstance(v, list) else v,
        "reverse": lambda v: list(reversed(v)) if isinstance(v, list) else v[::-1] if isinstance(v, str) else v,
    }

    def resolve_connected_inputs(
            self,
            node_id: str,
            edges: List[Dict[str, Any]],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        Resolves inputs from visual edge connections.

        This is where Visual Data Flow (drag-and-drop connections) gets
        translated into actual data passing. The edge's data_mappings
        configure exactly how fields are mapped.

        Args:
            node_id: Target node ID
            edges: All edges in the graph
            context: Execution context with node outputs

        Returns:
            Dictionary of resolved inputs from connections
        """
        connected_inputs: Dict[str, List[Any]] = {}
        merge_strategies: Dict[str, str] = {}

        # Find all edges targeting this node
        incoming_edges = [e for e in edges if e.get("target") == node_id]

        for edge in incoming_edges:
            source_node_id = edge.get("source")
            source_handle = edge.get("sourceHandle", "output")
            target_handle = edge.get("targetHandle", "input")
            data_mappings = edge.get("data_mappings", [])
            edge_merge_strategy = edge.get("merge_strategy")
            auto_map = edge.get("auto_map", True)

            # Get source node's output
            source_output = context.get_output(source_node_id)
            if source_output is None:
                logger.debug(f"No output from source node {source_node_id}")
                continue

            # Process explicit data mappings
            if data_mappings:
                for mapping in data_mappings:
                    source_field = mapping.get("source_field", source_handle)
                    target_field = mapping.get("target_field", target_handle)
                    transform = mapping.get("transform")
                    default_value = mapping.get("default_value")

                    value = self._extract_field(source_output, source_field)

                    # Apply default if value is None
                    if value is None and default_value is not None:
                        value = default_value

                    # Apply transform
                    if transform:
                        value = self._apply_transform(value, transform)

                    if target_field not in connected_inputs:
                        connected_inputs[target_field] = []
                    connected_inputs[target_field].append(value)

                    # Track merge strategy per handle
                    if edge_merge_strategy:
                        merge_strategies[target_field] = edge_merge_strategy
            else:
                # Default behavior (often triggered by "auto_map" edges)
                # If target_handle is just 'input', we might need to map it to a specific field.
                # React Flow often sends 'input' for the target handle if it's a generic connection.
                # However, if target_handle is 'input' and it's an auto_map connection, we usually 
                # want to pass the data exactly as extracted from the source_handle. 
                # For nodes like GeminiNode that expect a 'prompt', the frontend should ideally 
                # specify targetHandle='prompt'. If it doesn't, we map 'input' -> 'prompt' for common LLMs.
                value = self._extract_field(source_output, source_handle)
                
                # Dynamic auto-mapping for generic LLM inputs
                final_target = target_handle
                if target_handle == "input":
                    final_target = "prompt"

                if final_target not in connected_inputs:
                    connected_inputs[final_target] = []
                connected_inputs[final_target].append(value)

                if edge_merge_strategy:
                    merge_strategies[final_target] = edge_merge_strategy

        # Merge multiple inputs to same handle
        result = {}
        for handle, values in connected_inputs.items():
            if len(values) == 1:
                result[handle] = values[0]
            else:
                # Use explicit merge strategy if specified
                strategy = merge_strategies.get(handle)
                result[handle] = self._merge_inputs(values, handle, strategy)

        return result

    def _extract_field(self, data: Any, field_path: str) -> Any:
        """Extracts a field from nested data using dot notation."""
        if data is None:
            return None

        if field_path in (None, "", "output", "*"):
            return data

        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # Support array index like "items.0"
                if part.isdigit():
                    idx = int(part)
                    current = current[idx] if idx < len(current) else None
                else:
                    # Try to get field from all items
                    current = [item.get(part) if isinstance(item, dict) else None
                               for item in current]
            else:
                return None

            if current is None:
                return None

        return current

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Applies a transform to a value."""
        transform_fn = self.TRANSFORMS.get(transform)
        if transform_fn:
            try:
                return transform_fn(value)
            except Exception as e:
                logger.warning(f"Transform '{transform}' failed: {e}")
                return value
        return value

    def _merge_inputs(
            self,
            values: List[Any],
            handle: str,
            explicit_strategy: Optional[str] = None
    ) -> Any:
        """
        Merges multiple inputs to the same handle.

        Strategy can be explicitly set via edge configuration,
        or inferred from value types.
        """
        if not values:
            return None

        # Filter None values
        values = [v for v in values if v is not None]
        if not values:
            return None

        # Use explicit strategy if provided
        if explicit_strategy and explicit_strategy in self.MERGE_STRATEGIES:
            return self.MERGE_STRATEGIES[explicit_strategy](values)

        # Determine merge strategy based on types
        all_strings = all(isinstance(v, str) for v in values)
        all_lists = all(isinstance(v, list) for v in values)
        all_dicts = all(isinstance(v, dict) for v in values)

        if all_strings:
            return self.MERGE_STRATEGIES["concatenate"](values)
        elif all_lists:
            # Flatten lists
            result = []
            for v in values:
                result.extend(v)
            return result
        elif all_dicts:
            return self.MERGE_STRATEGIES["merge_dict"](values)
        else:
            return self.MERGE_STRATEGIES["array"](values)


# WORKFLOW EXECUTOR

class WorkflowExecutor:
    """
    Graph Execution Engine.

    Features:
    - Visual data flow via edge data_mappings
    - Race condition protection with async locks
    - Node alias resolution
    - Cost tracking per execution
    - Execution order tracking for @previous reference
    """

    _circuit_breaker = CircuitBreaker()

    def __init__(
            self,
            graph_definition: Dict[str, Any],
            global_vars: Optional[Dict[str, Any]] = None,
            max_parallel: int = 10,
            max_retries: int = 3,
            base_retry_delay: float = 1.0
    ):
        # Parse graph
        self.nodes = {n["id"]: n for n in graph_definition.get("nodes", [])}
        self.edges = graph_definition.get("edges", [])
        self.global_vars = global_vars or {}

        # Configuration
        self.max_parallel = max_parallel
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay

        # Build adjacency with data mappings
        self.adjacency: Dict[str, List[Dict[str, Any]]] = {}
        for edge in self.edges:
            source = edge["source"]
            if source not in self.adjacency:
                self.adjacency[source] = []
            self.adjacency[source].append({
                "target": edge["target"],
                "sourceHandle": edge.get("sourceHandle"),
                "targetHandle": edge.get("targetHandle"),
                "data_mappings": edge.get("data_mappings", [])
            })

        # Calculate in-degrees
        self.in_degree: Dict[str, int] = {}
        for edge in self.edges:
            target = edge["target"]
            self.in_degree[target] = self.in_degree.get(target, 0) + 1

        # Execution state (reset per run)
        self.visit_count: Dict[str, int] = {}
        self.execution_semaphore: Optional[asyncio.Semaphore] = None

        # Async lock for visit count
        self._visit_lock: asyncio.Lock = asyncio.Lock()

        # Execution order tracking
        self._execution_order: List[str] = []

        # Services
        self.resolver = InputResolver(self.nodes)
        self.data_mapper = DataMappingResolver()
        self.registry = get_registry()

        # Traces and metrics
        self.traces: List[NodeTrace] = []
        self._trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

        # Aggregate cost tracking
        self._total_cost = Decimal("0")
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    async def run(
            self,
            execution_id: UUID,
            initial_input: Dict[str, Any],
            db: AsyncSession,
            user_id: UUID,
            workflow_id: UUID,
            resume_node_id: Optional[str] = None,
            checkpoint_data: Optional[Dict[str, Any]] = None,
            trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
            single_node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute the workflow graph."""
        logger.info(f"Starting execution: {execution_id}")

        # Reset per-execution state
        self.visit_count = {}
        self.traces = []
        self._execution_order = []
        self._total_cost = Decimal("0")
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self.execution_semaphore = asyncio.Semaphore(self.max_parallel)

        # Create context
        context = create_execution_context(
            workflow_id=str(workflow_id),
            execution_id=str(execution_id),
            user_id=user_id,
            global_vars=self.global_vars,
            checkpoint_data=checkpoint_data
        )

        self._trace_callback = trace_callback

        # Single-node isolation run bypass
        if single_node_id:
            node_def = self.nodes.get(single_node_id)
            if not node_def:
                raise ValueError(f"Target node {single_node_id} not found in graph")
            
            output = await self._execute_node(
                node_id=single_node_id,
                node_def=node_def,
                dynamic_input=initial_input,
                loop_item=None,
                db=db,
                context=context
            )
            self._execution_order.append(single_node_id)
            await context.transition_state(ContextState.FINALIZING)
            await context.transition_state(ContextState.COMPLETED)
            return self._build_result(context)

        try:
            # Determine entry point
            if resume_node_id:
                queue = [
                    (edge["target"], {}, None)
                    for edge in self.adjacency.get(resume_node_id, [])
                ]
            else:
                start_node_id = self._find_start_node()
                if not start_node_id:
                    raise ValueError("Workflow missing startNode")
                queue = [(start_node_id, initial_input, None)]

            # Main execution loop
            while queue:
                node_id, dynamic_input, loop_item = queue.pop(0)
                node_def = self.nodes.get(node_id)

                if not node_def:
                    logger.warning(f"Node {node_id} not found in graph")
                    continue

                # Join synchronization with lock
                async with self._visit_lock:
                    self.visit_count[node_id] = self.visit_count.get(node_id, 0) + 1
                    current_visits = self.visit_count[node_id]
                    required_visits = self.in_degree.get(node_id, 1)

                    if current_visits < required_visits:
                        logger.debug(
                            f"Node {node_id} waiting for upstream "
                            f"({current_visits}/{required_visits})"
                        )
                        continue

                # Execute node
                output = await self._execute_node(
                    node_id=node_id,
                    node_def=node_def,
                    dynamic_input=dynamic_input,
                    loop_item=loop_item,
                    db=db,
                    context=context
                )

                # Track execution order
                self._execution_order.append(node_id)

                # Handle special outputs
                selected_branch = output.get("selected_branch")

                if selected_branch == "paused":
                    await context.transition_state(ContextState.PAUSED)
                    return self._build_result(context)

                if selected_branch == "completed":
                    continue

                # Get next nodes
                next_edges = self.adjacency.get(node_id, [])

                # Handle parallel branching
                if node_def["type"] == "parallelNode" or (
                        len(next_edges) > 1 and not selected_branch
                ):
                    await self._execute_parallel_branches(
                        edges=next_edges,
                        output=output,
                        loop_item=loop_item,
                        db=db,
                        context=context
                    )
                    continue

                # Handle loop iteration
                if node_def["type"] == "loopNode" and selected_branch == "start":
                    items = output.get("items", [])
                    is_parallel = output.get("parallel", False)
                    loop_edge = next(
                        (e for e in next_edges if e["sourceHandle"] == "start"),
                        None
                    )

                    if loop_edge and items:
                        if is_parallel:
                            await self._execute_parallel_loop(
                                edge=loop_edge,
                                items=items,
                                output=output,
                                max_concurrency=output.get("max_concurrency", 5),
                                db=db,
                                context=context
                            )
                        else:
                            for item in items:
                                queue.append((loop_edge["target"], output, item))
                    continue

                # Standard sequential traversal
                for edge in next_edges:
                    if not selected_branch or edge.get("sourceHandle") == selected_branch:
                        queue.append((edge["target"], output, loop_item))

            # Success
            await context.transition_state(ContextState.FINALIZING)
            await context.transition_state(ContextState.COMPLETED)

            logger.info(f"Execution completed: {execution_id}")
            return self._build_result(context)

        except Exception as e:
            logger.error(f"Execution failed: {execution_id} - {e}")
            await context.transition_state(ContextState.FAILED)
            raise

    def _build_result(self, context: ExecutionContext) -> Dict[str, Any]:
        """Builds the final result with cost summary."""
        return {
            **context.node_outputs,
            "_metadata": {
                "execution_id": context.execution_id,
                "workflow_id": context.workflow_id,
                "state": context.state.name,
                "metrics": context.metrics,
                "cost_summary": {
                    "total_cost_usd": str(self._total_cost),
                    "total_input_tokens": self._total_input_tokens,
                    "total_output_tokens": self._total_output_tokens
                }
            }
        }

    def _find_start_node(self) -> Optional[str]:
        # First try to find explicit startNode
        for node_id, node in self.nodes.items():
            node_type = node.get("type") or node.get("data", {}).get("type")
            if node_type == "startNode":
                return node_id
        
        # Fallback: Find nodes with no incoming edges
        for node_id in self.nodes.keys():
            if self.in_degree.get(node_id, 0) == 0:
                return node_id
                
        return None

    async def _execute_node(
            self,
            node_id: str,
            node_def: Dict[str, Any],
            dynamic_input: Dict[str, Any],
            loop_item: Any,
            db: AsyncSession,
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Execute a single node with enhanced input resolution."""
        # Frontend custom nodes store the actual backend node type in data.type
        node_type = node_def.get("data", {}).get("type")
        if not node_type or node_type == "custom":
            node_type = node_def.get("type", "unknown")

        # Check if the node is configured to use its pinned output
        node_data = node_def.get("data", {})
        if node_data.get("use_pinned") and "pinned_output" in node_data:
            output = node_data.get("pinned_output")
            
            await self._emit_trace({
                "node_id": node_id,
                "status": "SUCCESS",
                "duration_ms": 0,
                "output": output
            })
            return output

        # Circuit breaker check
        if not await self._circuit_breaker.can_execute(node_type):
            raise NodeExecutionError(
                message=f"Circuit breaker open for {node_type}",
                node_type=node_type,
                node_id=node_id,
                retryable=False
            )

        # STEP 1: Resolve inputs from VISUAL CONNECTIONS
        connected_inputs = self.data_mapper.resolve_connected_inputs(
            node_id=node_id,
            edges=self.edges,
            context=context
        )

        # STEP 2: Resolve inputs from STATIC CONFIG (with Jinja2)
        node_data = node_def.get("data", {})
        static_config = node_data.get("inputs", {}).copy()
        
        # Merge top-level data fields that are not structural metadata
        ignore_keys = {"inputs", "fields", "outputs", "type", "display_name", "icon", "category", "description", "label", "outputs_schema", "version", "tags", "connection_id"}
        for k, v in node_data.items():
            if k not in ignore_keys and k not in static_config:
                static_config[k] = v
                
        # Handle connection_id explicitly if not in inputs but in data
        if "connection_id" in node_data and "connection_id" not in static_config:
            static_config["connection_id"] = node_data["connection_id"]

        resolved_config = self.resolver.resolve(
            config=static_config,
            context_data=context.node_outputs,
            loop_item=loop_item,
            global_vars=self.global_vars,
            execution_order=self._execution_order
        )

        # STEP 3: MERGE - Connected inputs first, then static config overrides
        combined_input = {**connected_inputs, **resolved_config, **dynamic_input}

        # Get node instance
        try:
            node_instance = self.registry.get_node(node_type)
        except (NodeNotFoundError, ValueError):
            raise NodeExecutionError(
                message=f"Unknown node type: {node_type}",
                node_type=node_type,
                node_id=node_id,
                retryable=False
            )

        # Execute with retry
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            trace = NodeTrace(
                node_id=node_id,
                node_type=node_type,
                status="RUNNING",
                inputs=combined_input,
                attempt_number=attempt
            )

            try:
                await self._emit_trace({
                    "node_id": node_id,
                    "node_type": node_type,
                    "status": "RUNNING",
                    "attempt": attempt
                })

                async with self.execution_semaphore:
                    start_time = time.perf_counter()

                    output = await node_instance.run(
                        db=db,
                        context=context,
                        input_data=combined_input,
                        node_id=node_id
                    )

                    duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Record success
                trace.status = "SUCCESS"
                trace.outputs = output
                trace.duration_ms = duration_ms
                trace.completed_at = datetime.now(timezone.utc)

                # Extract cost info if present
                if "usage" in output:
                    usage = output["usage"]
                    trace.input_tokens = usage.get("input_tokens", 0)
                    trace.output_tokens = usage.get("output_tokens", 0)
                    trace.cost_usd = Decimal(str(usage.get("cost_usd", 0)))

                    # Aggregate
                    self._total_input_tokens += trace.input_tokens
                    self._total_output_tokens += trace.output_tokens
                    self._total_cost += trace.cost_usd

                self.traces.append(trace)
                await self._persist_trace(db, context.execution_id, trace)

                # Update context
                if loop_item is not None:
                    await context.set_scoped_output(
                        node_id=node_id,
                        scope_key=f"item_{hash(str(loop_item)) % 10000}",
                        output=output
                    )
                else:
                    await context.set_output_async(
                        node_id=node_id,
                        output=output,
                        duration_ms=duration_ms,
                        attempt_number=attempt
                    )

                await self._circuit_breaker.record_success(node_type)

                await self._emit_trace({
                    "node_id": node_id,
                    "status": "SUCCESS",
                    "duration_ms": duration_ms
                })

                return output

            except NodeExecutionError as e:
                last_error = e
                trace.status = "FAILED"
                trace.error_message = str(e)
                trace.completed_at = datetime.now(timezone.utc)
                self.traces.append(trace)
                await self._persist_trace(db, context.execution_id, trace)

                await self._emit_trace({
                    "node_id": node_id,
                    "status": "FAILED",
                    "error": str(e),
                    "attempt": attempt
                })

                if not e.retryable or attempt >= self.max_retries:
                    await self._circuit_breaker.record_failure(node_type)
                    raise

                delay = (self.base_retry_delay * (2 ** (attempt - 1))) + random.uniform(0.1, 0.5)
                logger.warning(f"Node {node_id} failed (attempt {attempt}). Retrying in {delay:.2f}s")
                await asyncio.sleep(delay)

            except Exception as e:
                last_error = NodeExecutionError(
                    message=str(e),
                    node_type=node_type,
                    node_id=node_id,
                    retryable=True
                )
                trace.status = "FAILED"
                trace.error_message = str(e)
                trace.completed_at = datetime.now(timezone.utc)
                self.traces.append(trace)
                await self._persist_trace(db, context.execution_id, trace)

                await self._emit_trace({
                    "node_id": node_id,
                    "status": "FAILED",
                    "error": str(e),
                    "attempt": attempt
                })

                if attempt >= self.max_retries:
                    await self._circuit_breaker.record_failure(node_type)
                    raise last_error

                delay = (self.base_retry_delay * (2 ** (attempt - 1))) + random.uniform(0.1, 0.5)
                await asyncio.sleep(delay)

        raise last_error or NodeExecutionError(
            message="Execution failed",
            node_type=node_type,
            node_id=node_id,
            retryable=False
        )

    async def _execute_parallel_branches(
            self,
            edges: List[Dict[str, Any]],
            output: Dict[str, Any],
            loop_item: Any,
            db: AsyncSession,
            context: ExecutionContext
    ) -> None:
        """Execute multiple branches in parallel."""
        async def execute_branch(edge: Dict[str, Any]) -> None:
            target_id = edge["target"]
            target_def = self.nodes.get(target_id)
            if target_def:
                await self._execute_node(
                    node_id=target_id,
                    node_def=target_def,
                    dynamic_input=output,
                    loop_item=loop_item,
                    db=db,
                    context=context
                )

        results = await asyncio.gather(
            *[execute_branch(edge) for edge in edges],
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                raise result

    async def _execute_parallel_loop(
            self,
            edge: Dict[str, Any],
            items: List[Any],
            output: Dict[str, Any],
            max_concurrency: int,
            db: AsyncSession,
            context: ExecutionContext
    ) -> None:
        """Execute loop iterations in parallel."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def execute_item(item: Any) -> None:
            async with semaphore:
                target_id = edge["target"]
                target_def = self.nodes.get(target_id)
                if target_def:
                    await self._execute_node(
                        node_id=target_id,
                        node_def=target_def,
                        dynamic_input=output,
                        loop_item=item,
                        db=db,
                        context=context
                    )

        results = await asyncio.gather(
            *[execute_item(item) for item in items],
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                raise result

    async def _emit_trace(self, data: Dict[str, Any]) -> None:
        """Emit trace event via callback."""
        if self._trace_callback:
            try:
                await self._trace_callback({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **data
                })
            except Exception as e:
                logger.warning(f"Trace callback failed: {e}")

    async def _persist_trace(
            self,
            db: AsyncSession,
            execution_id: str,
            trace: NodeTrace
    ) -> None:
        """
        Persists a single node trace immediately, so the /timeline endpoint
        reflects live progress instead of only appearing after the whole
        workflow finishes.
        """
        try:
            db.add(NodeExecutionTrace(
                execution_id=UUID(execution_id),
                node_id=trace.node_id,
                node_type=trace.node_type,
                status=trace.status,
                inputs=trace._mask_secrets(trace.inputs),
                outputs=trace._mask_secrets(trace.outputs) if trace.outputs else {},
                error_message=trace.error_message,
                duration_ms=trace.duration_ms,
                attempt_number=trace.attempt_number,
            ))
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist node trace for {trace.node_id}: {e}")
            await db.rollback()

    def get_traces(self) -> List[Dict[str, Any]]:
        """Returns all execution traces."""
        return [t.to_dict() for t in self.traces]

    def get_cost_summary(self) -> Dict[str, Any]:
        """Returns cost summary for this execution."""
        return {
            "total_cost_usd": str(self._total_cost),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "traces_count": len(self.traces)
        }

    @classmethod
    def get_circuit_status(cls) -> Dict[str, Any]:
        """Returns circuit breaker status for monitoring."""
        return cls._circuit_breaker.get_status()