from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from pydantic import ValidationError
from loguru import logger

from src.schemas.workflow.workflow import WorkflowGraph, Node, Edge


# ============================================================
# CONFIGURATION
# ============================================================

class ValidationSeverity(str, Enum):
    """Validation issue severity."""
    ERROR = "error"      # Blocks execution
    WARNING = "warning"  # May cause issues
    INFO = "info"        # Informational


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    severity: ValidationSeverity
    message: str
    node_id: Optional[str] = None
    field: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary."""
        return {
            "severity": self.severity.value,
            "message": self.message,
            "node_id": self.node_id,
            "field": self.field,
            "suggestion": self.suggestion
        }


@dataclass
class ValidationResult:
    """Complete validation result."""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def add_error(
            self,
            message: str,
            node_id: str = None,
            field: str = None,
            suggestion: str = None
    ):
        """Adds an error."""
        self.is_valid = False
        self.errors.append(message)
        self.issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            message=message,
            node_id=node_id,
            field=field,
            suggestion=suggestion
        ))

    def add_warning(
            self,
            message: str,
            node_id: str = None,
            field: str = None,
            suggestion: str = None
    ):
        """Adds a warning."""
        self.warnings.append(message)
        self.issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            message=message,
            node_id=node_id,
            field=field,
            suggestion=suggestion
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats
        }


# ============================================================
# GRAPH VALIDATION SERVICE
# ============================================================

class GraphValidationService:
    """
    World-Class Static Analysis for Workflow Graphs.

    Validation Pipeline:
    1. Structure validation (Pydantic)
    2. Entry point validation
    3. Node type validation
    4. Manifest field validation
    5. Edge reference validation
    6. Handle integrity validation
    7. Cycle detection
    8. Orphan detection
    9. Reachability analysis

    Features:
    - Errors vs warnings distinction
    - Detailed error messages
    - Fix suggestions
    - Graph statistics
    """

    # Node types that allow self-loops
    LOOP_ALLOWED_TYPES = {"loopNode", "parallelNode"}

    # Node types that must have outgoing edges
    MUST_HAVE_OUTPUT = {"startNode", "filterNode", "routerNode", "loopNode"}

    # Node types that are valid terminals
    TERMINAL_TYPES = {"waitNode", "webhookNode"}

    @classmethod
    def validate_graph(cls, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Performs comprehensive graph validation.

        Args:
            graph_data: Raw graph definition

        Returns:
            Validation result dictionary
        """
        result = ValidationResult()

        try:
            # 1. STRUCTURE VALIDATION
            graph = cls._validate_structure(graph_data, result)
            if not graph:
                return result.to_dict()

            # Build lookup structures
            nodes_map = {n.id: n for n in graph.nodes}
            adjacency = cls._build_adjacency_list(graph)
            reverse_adjacency = cls._build_reverse_adjacency(graph)

            # 2. ENTRY POINT VALIDATION
            start_nodes = cls._validate_entry_points(graph, result)

            # 3. NODE TYPE VALIDATION
            cls._validate_node_types(graph, result)

            # 4. MANIFEST FIELD VALIDATION
            cls._validate_manifest_fields(graph, result)

            # 5. EDGE REFERENCE VALIDATION
            cls._validate_edge_references(graph, nodes_map, result)

            # 6. HANDLE INTEGRITY VALIDATION
            cls._validate_handles(graph, result)

            # 7. CYCLE DETECTION
            if start_nodes:
                cls._detect_cycles(start_nodes[0].id, adjacency, nodes_map, result)

            # 8. ORPHAN DETECTION
            cls._detect_orphans(graph, adjacency, reverse_adjacency, result)

            # 9. REACHABILITY ANALYSIS
            if start_nodes:
                cls._analyze_reachability(
                    start_nodes[0].id,
                    adjacency,
                    nodes_map,
                    result
                )

            # 10. COMPUTE STATISTICS
            result.stats = cls._compute_stats(graph, adjacency)

            return result.to_dict()

        except ValidationError as ve:
            result.add_error(f"Schema validation failed: {str(ve)}")
            return result.to_dict()

        except Exception as e:
            logger.error(f"Graph validation error: {e}")
            result.add_error(f"Validation error: {str(e)}")
            return result.to_dict()

    # ============================================================
    # VALIDATION STEPS
    # ============================================================

    @classmethod
    def _validate_structure(
            cls,
            graph_data: Dict[str, Any],
            result: ValidationResult
    ) -> Optional[WorkflowGraph]:
        """Validates graph structure with Pydantic."""
        try:
            return WorkflowGraph.model_validate(graph_data)
        except ValidationError as e:
            for error in e.errors():
                field = ".".join(str(x) for x in error["loc"])
                result.add_error(
                    f"Invalid structure at '{field}': {error['msg']}",
                    field=field
                )
            return None

    @classmethod
    def _validate_entry_points(
            cls,
            graph: WorkflowGraph,
            result: ValidationResult
    ) -> List[Node]:
        """Validates workflow entry points."""
        start_nodes = [n for n in graph.nodes if n.resolved_type == "startNode"]

        if len(start_nodes) == 0:
            result.add_error(
                "Graph is missing a 'startNode'",
                suggestion="Add a Start node as the entry point"
            )
        elif len(start_nodes) > 1:
            node_ids = [n.id for n in start_nodes]
            result.add_error(
                f"Multiple start nodes detected: {node_ids}",
                suggestion="Remove extra start nodes, only one is allowed"
            )

        return start_nodes

    @classmethod
    def _validate_node_types(
            cls,
            graph: WorkflowGraph,
            result: ValidationResult
    ) -> None:
        """Validates node types against registry."""
        try:
            from src.services.workflow_engine.registry import NodeRegistry

            for node in graph.nodes:
                try:
                    NodeRegistry.get_node(node.resolved_type)
                except ValueError:
                    result.add_error(
                        f"Unknown node type '{node.resolved_type}'",
                        node_id=node.id,
                        suggestion=f"Check if '{node.resolved_type}' is registered"
                    )
        except ImportError:
            # Registry not available, skip validation
            pass

    @classmethod
    def _validate_manifest_fields(
            cls,
            graph: WorkflowGraph,
            result: ValidationResult
    ) -> None:
        """Validates node fields against manifests."""
        try:
            from src.services.workflow_engine.registry import NodeRegistry

            for node in graph.nodes:
                try:
                    node_class = NodeRegistry.get_node(node.resolved_type)
                    manifest = node_class.get_manifest()
                except Exception:
                    continue

                # Check if this node has a pinned output and is set to use it
                is_pinned = False
                if node.data:
                    data_dict = getattr(node.data, 'model_extra', {}) or {}
                    if not isinstance(data_dict, dict):
                        data_dict = {}
                    raw_dict = node.data.__dict__ if hasattr(node.data, '__dict__') else {}
                    
                    if (data_dict.get("use_pinned") or raw_dict.get("use_pinned")) and ("pinned_output" in data_dict or "pinned_output" in raw_dict):
                        is_pinned = True

                if is_pinned:
                    continue

                # Get user inputs
                user_inputs = {}
                if node.data:
                    # 1. Get from 'inputs' attribute if present
                    inputs_val = getattr(node.data, 'inputs', {}) or {}
                    if hasattr(node.data, '__dict__'):
                        inputs_val = node.data.__dict__.get('inputs', {}) or {}
                    
                    if isinstance(inputs_val, dict):
                        user_inputs = inputs_val.copy()
                    else:
                        user_inputs = {}

                    # 2. Merge top-level extra fields / attributes
                    # Exclude fields that are structural / internal UI metadata
                    ignore_keys = {"inputs", "fields", "outputs", "type", "display_name", "icon", "category", "description", "label", "outputs_schema", "version", "tags"}
                    
                    # Merge Pydantic v2 model_extra fields
                    model_extra = getattr(node.data, 'model_extra', None)
                    if isinstance(model_extra, dict):
                        for k, v in model_extra.items():
                            if k not in ignore_keys and k not in user_inputs:
                                user_inputs[k] = v
                                
                    # Merge from raw dictionary
                    if hasattr(node.data, '__dict__'):
                        for k, v in node.data.__dict__.items():
                            if k not in ignore_keys and k not in user_inputs and not k.startswith('_'):
                                user_inputs[k] = v

                # Find connected inputs for this node
                connected_inputs = set()
                for edge in graph.edges:
                    if edge.target == node.id:
                        if edge.targetHandle:
                            connected_inputs.add(edge.targetHandle)
                        else:
                            connected_inputs.add("input")

                # Check required fields
                for field in manifest.get("fields", []):
                    field_name = field.get("name")
                    is_required = field.get("required", False)

                    # A required field is satisfied if configured statically or connected dynamically
                    is_satisfied = (field_name in user_inputs and user_inputs[field_name] not in (None, "")) or (field_name in connected_inputs) or ("input" in connected_inputs)

                    if is_required and not is_satisfied:
                        # Check if there's a default
                        if "default" not in field:
                            result.add_error(
                                f"Missing required field '{field.get('label', field_name)}'",
                                node_id=node.id,
                                field=field_name,
                                suggestion=f"Configure the '{field.get('label', field_name)}' field"
                            )

                    # Validate field type if value exists
                    if field_name in user_inputs:
                        cls._validate_field_type(
                            node.id,
                            field,
                            user_inputs[field_name],
                            result
                        )

        except ImportError:
            pass

    @classmethod
    def _validate_field_type(
            cls,
            node_id: str,
            field: Dict[str, Any],
            value: Any,
            result: ValidationResult
    ) -> None:
        """Validates field value against expected type."""
        field_name = field.get("name")
        field_type = field.get("type", "text")

        if value is None:
            return

        # Skip template strings
        if isinstance(value, str) and "{{" in value:
            return

        try:
            if field_type == "number":
                if not isinstance(value, (int, float)):
                    float(value)
            elif field_type == "boolean":
                if not isinstance(value, bool):
                    if str(value).lower() not in ("true", "false", "1", "0", "yes", "no"):
                        raise ValueError("Invalid boolean")
            elif field_type == "json_editor":
                if isinstance(value, str):
                    import json
                    json.loads(value)
        except (ValueError, TypeError):
            result.add_warning(
                f"Field '{field_name}' has unexpected type",
                node_id=node_id,
                field=field_name,
                suggestion=f"Expected {field_type}, got {type(value).__name__}"
            )

    @classmethod
    def _validate_edge_references(
            cls,
            graph: WorkflowGraph,
            nodes_map: Dict[str, Node],
            result: ValidationResult
    ) -> None:
        """Validates edge source/target references."""
        for edge in graph.edges:
            if edge.source not in nodes_map:
                result.add_error(
                    f"Edge '{edge.id}' references non-existent source '{edge.source}'",
                    suggestion="Remove the edge or add the missing node"
                )

            if edge.target not in nodes_map:
                result.add_error(
                    f"Edge '{edge.id}' references non-existent target '{edge.target}'",
                    suggestion="Remove the edge or add the missing node"
                )

    @classmethod
    def _validate_handles(
            cls,
            graph: WorkflowGraph,
            result: ValidationResult
    ) -> None:
        """Validates connection handles against manifests."""
        try:
            from src.services.workflow_engine.registry import NodeRegistry

            for node in graph.nodes:
                try:
                    node_class = NodeRegistry.get_node(node.resolved_type)
                    manifest = node_class.get_manifest()
                except Exception:
                    continue

                valid_outputs = set(manifest.get("outputs", []))

                # Check outgoing edges
                out_edges = [e for e in graph.edges if e.source == node.id]

                for edge in out_edges:
                    if edge.sourceHandle and valid_outputs:
                        if edge.sourceHandle not in valid_outputs:
                            result.add_warning(
                                f"Invalid output handle '{edge.sourceHandle}'",
                                node_id=node.id,
                                suggestion=f"Valid handles: {', '.join(valid_outputs)}"
                            )

                # Router-specific validation
                if node.resolved_type == "routerNode":
                    cls._validate_router_branches(node, out_edges, result)

        except ImportError:
            pass

    @classmethod
    def _validate_router_branches(
            cls,
            node: Node,
            out_edges: List[Edge],
            result: ValidationResult
    ) -> None:
        """Validates router node branches."""
        configured_branches = []
        if node.data:
            data_dict = node.data.__dict__ if hasattr(node.data, '__dict__') else {}
            configured_branches = data_dict.get("branches", [])

        connected_handles = {e.sourceHandle for e in out_edges if e.sourceHandle}

        for branch in configured_branches:
            if branch not in connected_handles:
                result.add_warning(
                    f"Unconnected branch '{branch}'",
                    node_id=node.id,
                    suggestion=f"Connect the '{branch}' output or remove it"
                )

    @classmethod
    def _detect_cycles(
            cls,
            start_id: str,
            adjacency: Dict[str, List[str]],
            nodes_map: Dict[str, Node],
            result: ValidationResult
    ) -> None:
        """Detects cycles using DFS."""
        visited = set()
        rec_stack = set()
        cycle_path = []

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            cycle_path.append(node_id)

            for neighbor in adjacency.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Check if cycle is allowed
                    node = nodes_map.get(node_id)
                    if node and node.resolved_type not in cls.LOOP_ALLOWED_TYPES:
                        # Find cycle
                        cycle_start = cycle_path.index(neighbor)
                        cycle_nodes = cycle_path[cycle_start:]
                        result.add_error(
                            f"Illegal cycle detected: {' -> '.join(cycle_nodes + [neighbor])}",
                            node_id=node_id,
                            suggestion="Use a Loop node for intentional iteration"
                        )
                        return True

            cycle_path.pop()
            rec_stack.remove(node_id)
            return False

        dfs(start_id)

    @classmethod
    def _detect_orphans(
            cls,
            graph: WorkflowGraph,
            adjacency: Dict[str, List[str]],
            reverse_adjacency: Dict[str, List[str]],
            result: ValidationResult
    ) -> None:
        """Detects orphan nodes."""
        for node in graph.nodes:
            if node.resolved_type == "startNode":
                continue

            # Check if node has no incoming edges
            if not reverse_adjacency.get(node.id):
                result.add_warning(
                    f"Node '{node.id}' has no incoming connections",
                    node_id=node.id,
                    suggestion="Connect this node or remove it"
                )

            # Check if non-terminal node has no outgoing edges
            if node.resolved_type in cls.MUST_HAVE_OUTPUT:
                if not adjacency.get(node.id):
                    result.add_warning(
                        f"Node '{node.id}' ({node.resolved_type}) has no outgoing connections",
                        node_id=node.id,
                        suggestion="Connect this node to downstream nodes"
                    )

    @classmethod
    def _analyze_reachability(
            cls,
            start_id: str,
            adjacency: Dict[str, List[str]],
            nodes_map: Dict[str, Node],
            result: ValidationResult
    ) -> None:
        """Analyzes node reachability from start."""
        visited = set()
        queue = [start_id]

        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            queue.extend(adjacency.get(node_id, []))

        # Find unreachable nodes
        for node_id, node in nodes_map.items():
            if node_id not in visited:
                result.add_warning(
                    f"Node '{node_id}' is unreachable from start",
                    node_id=node_id,
                    suggestion="Connect this node to the workflow or remove it"
                )

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _build_adjacency_list(graph: WorkflowGraph) -> Dict[str, List[str]]:
        """Builds forward adjacency list."""
        adjacency = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adjacency:
                adjacency[edge.source].append(edge.target)
        return adjacency

    @staticmethod
    def _build_reverse_adjacency(graph: WorkflowGraph) -> Dict[str, List[str]]:
        """Builds reverse adjacency list."""
        reverse = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.target in reverse:
                reverse[edge.target].append(edge.source)
        return reverse

    @staticmethod
    def _compute_stats(
            graph: WorkflowGraph,
            adjacency: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Computes graph statistics."""
        node_types = {}
        for node in graph.nodes:
            node_types[node.resolved_type] = node_types.get(node.resolved_type, 0) + 1

        # Find max depth (longest path from start)
        max_depth = 0
        start_nodes = [n for n in graph.nodes if n.resolved_type == "startNode"]

        if start_nodes:
            visited = {}
            queue = [(start_nodes[0].id, 0)]

            while queue:
                node_id, depth = queue.pop(0)
                if node_id in visited:
                    continue
                visited[node_id] = depth
                max_depth = max(max_depth, depth)

                for neighbor in adjacency.get(node_id, []):
                    queue.append((neighbor, depth + 1))

        return {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "node_types": node_types,
            "max_depth": max_depth,
            "has_start_node": any(n.resolved_type == "startNode" for n in graph.nodes),
            "is_connected": max_depth > 0 or len(graph.nodes) <= 1
        }