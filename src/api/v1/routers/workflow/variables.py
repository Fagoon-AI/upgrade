from typing import List, Dict, Any, Optional, Set
from uuid import UUID
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow
from src.dao.workflow_dao import WorkflowDAO
from src.services.workflow_engine.registry import NodeRegistry
from src.schemas.workflow.response import APIResponse


router = APIRouter(prefix="/variables", tags=["Variables"])


# SCHEMAS

class VariableType(str, Enum):
    """Supported variable types for type checking."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ANY = "any"


class VariableDefinition(BaseModel):
    """A single variable available for use."""
    name: str = Field(..., description="Variable name")
    display_name: str = Field(..., description="Human-readable name")
    type: VariableType = Field(default=VariableType.ANY, description="Variable type")
    path: str = Field(..., description="Full path: steps['node-id'].field")
    template: str = Field(..., description="Jinja2 template: {{ steps['node-id'].field }}")
    shorthand: Optional[str] = Field(None, description="Shorthand: {{ NodeLabel.field }}")
    expandable: bool = Field(False, description="Whether this contains nested fields")
    hint: Optional[str] = Field(None, description="Usage hint")
    children: List["VariableDefinition"] = Field(default_factory=list, description="Nested variables")


class NodeVariables(BaseModel):
    """Variables available from a single node."""
    node_id: str
    node_label: str
    node_type: str
    icon: Optional[str] = None
    variables: List[VariableDefinition]


class HandleDefinition(BaseModel):
    """Input or output handle for a node."""
    id: str = Field(..., description="Handle identifier")
    label: str = Field(..., description="Display label")
    type: VariableType = Field(default=VariableType.ANY)
    required: bool = Field(False)
    accepts_multiple: bool = Field(False, description="Can accept multiple connections")
    description: Optional[str] = None


class NodeHandles(BaseModel):
    """All handles for a node."""
    node_id: str
    node_type: str
    node_label: str
    input_handles: List[HandleDefinition]
    output_handles: List[HandleDefinition]


class ConnectionValidation(BaseModel):
    """Result of validating a connection."""
    is_valid: bool
    source_type: VariableType
    target_type: VariableType
    warning: Optional[str] = None
    suggestion: Optional[str] = None


class SyntaxHelp(BaseModel):
    """Variable syntax help."""
    full: str = Field(default="{{ steps['node-id'].field }}")
    shorthand: str = Field(default="{{ NodeLabel.field }}")
    previous: str = Field(default="{{ @previous.output }}")
    loop_item: str = Field(default="{{ item }}")
    nested: str = Field(default="{{ steps['node-id'].field.nested.path }}")
    with_filter: str = Field(default="{{ steps['node-id'].field | trim | upper }}")
    with_default: str = Field(default="{{ steps['node-id'].field | default('fallback') }}")


class VariablesResponse(BaseModel):
    """Response for variables endpoint."""
    workflow_id: str
    target_node: Optional[str]
    nodes: List[NodeVariables]
    syntax_help: SyntaxHelp


class HandlesResponse(BaseModel):
    """Response for handles endpoint."""
    workflow_id: str
    nodes: List[NodeHandles]


# HELPERS

def _is_upstream(
        graph: Dict[str, Any],
        source_id: str,
        target_id: str
) -> bool:
    """
    Checks if source node is upstream of (can reach) target node.

    Uses BFS to traverse the graph.
    """
    edges = graph.get("edges", [])

    # Build adjacency list
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        src = edge.get("source")
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append(edge.get("target"))

    # BFS from source
    visited: Set[str] = set()
    queue = [source_id]

    while queue:
        current = queue.pop(0)
        if current == target_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adjacency.get(current, []))

    return False


def _humanize(name: str) -> str:
    """Converts snake_case or camelCase to Human Readable."""
    import re
    # Handle snake_case
    name = name.replace("_", " ")
    # Handle camelCase
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return name.title()


def _get_clean_label(label: str) -> str:
    """Creates a clean label for shorthand syntax."""
    return label.replace(" ", "").replace("-", "_")


def _infer_type(value: Any) -> VariableType:
    """Infers variable type from a value."""
    if isinstance(value, str):
        return VariableType.STRING
    elif isinstance(value, bool):
        return VariableType.BOOLEAN
    elif isinstance(value, (int, float)):
        return VariableType.NUMBER
    elif isinstance(value, list):
        return VariableType.ARRAY
    elif isinstance(value, dict):
        return VariableType.OBJECT
    return VariableType.ANY


def _get_manifest_outputs(node_type: str) -> tuple[List[str], Dict[str, Any]]:
    """Gets outputs and schema from node manifest."""
    try:
        node_class = NodeRegistry.get_node(node_type)
        manifest = node_class.get_manifest()
        outputs = manifest.get("outputs", ["output"])
        outputs_schema = manifest.get("outputs_schema", {})
        return outputs, outputs_schema
    except Exception:
        return ["output"], {}


def _get_manifest_handles(node_type: str) -> tuple[List[Dict], List[Dict]]:
    """Gets input and output handles from node manifest."""
    try:
        node_class = NodeRegistry.get_node(node_type)
        manifest = node_class.get_manifest()

        # Get explicit handles if defined
        input_handles = manifest.get("input_handles", [])
        output_handles = manifest.get("output_handles", [])

        # If no explicit handles, derive from fields and outputs
        if not input_handles:
            fields = manifest.get("fields", [])
            input_handles = [
                {
                    "id": f.get("name"),
                    "label": f.get("label", _humanize(f.get("name", ""))),
                    "type": _field_type_to_var_type(f.get("type", "text")),
                    "required": f.get("required", False)
                }
                for f in fields
                if f.get("name") not in ["connection_id"]  # Skip connection fields
            ]

        if not output_handles:
            outputs = manifest.get("outputs", ["output"])
            outputs_schema = manifest.get("outputs_schema", {})
            output_handles = [
                {
                    "id": o,
                    "label": _humanize(o),
                    "type": outputs_schema.get(o, {}).get("type", "any")
                }
                for o in outputs
            ]

        return input_handles, output_handles

    except Exception as e:
        logger.debug(f"Could not get manifest for {node_type}: {e}")
        return [], [{"id": "output", "label": "Output", "type": "any"}]


def _field_type_to_var_type(field_type: str) -> str:
    """Maps field type to variable type."""
    mapping = {
        "text": "string",
        "textarea": "string",
        "number": "number",
        "boolean": "boolean",
        "select": "string",
        "multi_select": "array",
        "json_editor": "object",
        "code_editor": "string",
        "list": "array",
    }
    return mapping.get(field_type, "any")


def _expand_schema_fields(
        schema: Dict[str, Any],
        node_id: str,
        clean_label: str,
        base_path: str = "",
        max_depth: int = 3,
        current_depth: int = 0
) -> List[VariableDefinition]:
    """
    Recursively expands schema into VariableDefinitions.

    This enables the Variable Picker to show nested fields.
    """
    if current_depth >= max_depth:
        return []

    variables = []
    properties = schema.get("properties", {})

    for field_name, field_schema in properties.items():
        full_path = f"{base_path}.{field_name}" if base_path else field_name
        field_type = field_schema.get("type", "any")
        var_type = VariableType(field_type) if field_type in VariableType.__members__.values() else VariableType.ANY

        var = VariableDefinition(
            name=full_path,
            display_name=_humanize(field_name),
            type=var_type,
            path=f"steps['{node_id}'].{full_path}",
            template=f"{{{{ steps['{node_id}'].{full_path} }}}}",
            shorthand=f"{{{{ {clean_label}.{full_path} }}}}",
            expandable=field_type in ["object", "array"],
            hint=field_schema.get("description")
        )

        # Recursively expand nested objects
        if field_type == "object" and "properties" in field_schema:
            var.children = _expand_schema_fields(
                field_schema,
                node_id,
                clean_label,
                full_path,
                max_depth,
                current_depth + 1
            )
        elif field_type == "array" and "items" in field_schema:
            item_schema = field_schema["items"]
            if item_schema.get("type") == "object" and "properties" in item_schema:
                # Show array item fields
                for item_name, item_field in item_schema["properties"].items():
                    item_path = f"{full_path}[*].{item_name}"
                    item_type = item_field.get("type", "any")
                    var.children.append(VariableDefinition(
                        name=item_path,
                        display_name=f"[item].{_humanize(item_name)}",
                        type=VariableType(item_type) if item_type in VariableType.__members__.values() else VariableType.ANY,
                        path=f"steps['{node_id}'].{item_path}",
                        template=f"{{{{ steps['{node_id}'].{item_path} }}}}",
                        shorthand=f"{{{{ {clean_label}.{item_path} }}}}",
                        expandable=False,
                        hint=item_field.get("description")
                    ))

        variables.append(var)

    return variables


# ENDPOINTS

@router.get(
    "/workflows/{workflow_id}/variables",
    response_model=APIResponse[VariablesResponse],
    summary="Get available variables",
    description="Returns all variables available for use in a workflow node"
)
async def get_available_variables(
        workflow_id: UUID,
        target_node_id: Optional[str] = Query(
            None,
            description="Target node - only show variables from upstream nodes"
        ),
        include_schema: bool = Query(
            True,
            description="Include type schema information"
        ),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns all available variables that can be used in a node.

    For the visual variable picker in the frontend.
    """
    # Get workflow
    dao = WorkflowDAO(db)
    workflow = await dao.get_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this workflow"
        )

    graph = workflow.graph_definition
    available_variables: List[NodeVariables] = []

    for node in graph.get("nodes", []):
        node_id = node["id"]
        node_type = node.get("type", "unknown")
        node_data = node.get("data", {})
        node_label = node_data.get("label", node_id)

        # Skip target node and nodes that come after it
        if target_node_id:
            if node_id == target_node_id:
                continue
            if not _is_upstream(graph, node_id, target_node_id):
                continue

        # Get outputs from manifest
        outputs, outputs_schema = _get_manifest_outputs(node_type)

        # Build variables
        variables: List[VariableDefinition] = []
        clean_label = _get_clean_label(node_label)

        # Special handling for startNode
        if node_type == "startNode":
            variables.append(VariableDefinition(
                name="initial_input",
                display_name="User Input",
                type=VariableType.OBJECT,
                path=f"steps['{node_id}'].initial_input",
                template=f"{{{{ steps['{node_id}'].initial_input }}}}",
                shorthand=f"{{{{ {clean_label}.input }}}}",
                expandable=True,
                hint="Access specific fields like: {{ steps['start-1'].initial_input.your_field }}"
            ))

            # Common start node fields
            for field_name in ["user_message", "execution_id", "timestamp"]:
                variables.append(VariableDefinition(
                    name=f"initial_input.{field_name}",
                    display_name=_humanize(field_name),
                    type=VariableType.STRING,
                    path=f"steps['{node_id}'].initial_input.{field_name}",
                    template=f"{{{{ steps['{node_id}'].initial_input.{field_name} }}}}",
                    shorthand=f"{{{{ {clean_label}.{field_name} }}}}"
                ))
        else:
            # Standard outputs
            for output_name in outputs:
                schema = outputs_schema.get(output_name, {})
                type_str = schema.get("type", "any")
                var_type = VariableType(type_str) if type_str in VariableType.__members__.values() else VariableType.ANY

                var_def = VariableDefinition(
                    name=output_name,
                    display_name=_humanize(output_name),
                    type=var_type,
                    path=f"steps['{node_id}'].{output_name}",
                    template=f"{{{{ steps['{node_id}'].{output_name} }}}}",
                    shorthand=f"{{{{ {clean_label}.{output_name} }}}}",
                    expandable=var_type in [VariableType.OBJECT, VariableType.ARRAY],
                    hint=schema.get("description")
                )

                # Expand nested fields from schema
                if include_schema and var_type == VariableType.OBJECT and "properties" in schema:
                    var_def.children = _expand_schema_fields(
                        schema,
                        node_id,
                        clean_label,
                        output_name,
                        max_depth=2
                    )
                elif include_schema and var_type == VariableType.ARRAY and "items" in schema:
                    item_schema = schema["items"]
                    if item_schema.get("type") == "object" and "properties" in item_schema:
                        var_def.children = _expand_schema_fields(
                            item_schema,
                            node_id,
                            clean_label,
                            f"{output_name}[*]",
                            max_depth=2
                        )

                variables.append(var_def)

        # Get icon from manifest
        icon = None
        try:
            node_class = NodeRegistry.get_node(node_type)
            manifest = node_class.get_manifest()
            icon = manifest.get("icon")
        except Exception:
            pass

        available_variables.append(NodeVariables(
            node_id=node_id,
            node_label=node_label,
            node_type=node_type,
            icon=icon,
            variables=variables
        ))

    return APIResponse(
        success=True,
        message=f"Found variables from {len(available_variables)} nodes",
        data=VariablesResponse(
            workflow_id=str(workflow_id),
            target_node=target_node_id,
            nodes=available_variables,
            syntax_help=SyntaxHelp()
        )
    )


@router.get(
    "/workflows/{workflow_id}/handles",
    response_model=APIResponse[HandlesResponse],
    summary="Get node handles",
    description="Returns all input/output handles for nodes in a workflow"
)
async def get_node_handles(
        workflow_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns input/output handles for all nodes in a workflow.

    Used by frontend for rendering connection points.
    """
    dao = WorkflowDAO(db)
    workflow = await dao.get_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )

    graph = workflow.graph_definition
    nodes_handles: List[NodeHandles] = []

    for node in graph.get("nodes", []):
        node_id = node["id"]
        node_type = node.get("type", "unknown")
        node_label = node.get("data", {}).get("label", node_id)

        input_handles_raw, output_handles_raw = _get_manifest_handles(node_type)

        input_handles = [
            HandleDefinition(
                id=h.get("id", "input"),
                label=h.get("label", "Input"),
                type=VariableType(h.get("type", "any")),
                required=h.get("required", False),
                accepts_multiple=h.get("accepts_multiple", False),
                description=h.get("description")
            )
            for h in input_handles_raw
        ]

        output_handles = [
            HandleDefinition(
                id=h.get("id", "output"),
                label=h.get("label", "Output"),
                type=VariableType(h.get("type", "any")),
                required=False,
                accepts_multiple=True,  # Outputs can always have multiple connections
                description=h.get("description")
            )
            for h in output_handles_raw
        ]

        nodes_handles.append(NodeHandles(
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            input_handles=input_handles,
            output_handles=output_handles
        ))

    return APIResponse(
        success=True,
        message=f"Found handles for {len(nodes_handles)} nodes",
        data=HandlesResponse(
            workflow_id=str(workflow_id),
            nodes=nodes_handles
        )
    )


class ConnectionValidationRequest(BaseModel):
    """Request to validate a connection."""
    source_node_id: str
    source_handle: str
    target_node_id: str
    target_handle: str


@router.post(
    "/workflows/{workflow_id}/validate-connection",
    response_model=APIResponse[ConnectionValidation],
    summary="Validate connection",
    description="Validates if a connection between two handles is valid"
)
async def validate_connection(
        workflow_id: UUID,
        request: ConnectionValidationRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Validates a proposed connection between two node handles.

    Checks:
    - Type compatibility
    - Graph validity (no cycles)
    - Required fields
    """
    dao = WorkflowDAO(db)
    workflow = await dao.get_by_id(workflow_id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    if workflow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )

    graph = workflow.graph_definition
    nodes_map = {n["id"]: n for n in graph.get("nodes", [])}

    # Get source and target nodes
    source_node = nodes_map.get(request.source_node_id)
    target_node = nodes_map.get(request.target_node_id)

    if not source_node or not target_node:
        return APIResponse(
            success=True,
            data=ConnectionValidation(
                is_valid=False,
                source_type=VariableType.ANY,
                target_type=VariableType.ANY,
                warning="Source or target node not found"
            )
        )

    # Get handle types
    source_type = VariableType.ANY
    target_type = VariableType.ANY

    _, source_outputs = _get_manifest_handles(source_node.get("type", "unknown"))
    target_inputs, _ = _get_manifest_handles(target_node.get("type", "unknown"))

    for handle in source_outputs:
        if handle.get("id") == request.source_handle:
            source_type = VariableType(handle.get("type", "any"))
            break

    for handle in target_inputs:
        if handle.get("id") == request.target_handle:
            target_type = VariableType(handle.get("type", "any"))
            break

    # Type compatibility matrix
    # any matches everything, same types match, string can become anything
    is_compatible = (
            source_type == VariableType.ANY or
            target_type == VariableType.ANY or
            source_type == target_type or
            source_type == VariableType.STRING  # String can be coerced
    )

    warning = None
    suggestion = None

    if not is_compatible:
        warning = f"Type mismatch: {source_type.value} → {target_type.value}"
        suggestion = "Consider adding a transform to convert the data type"

    # Check for cycle
    if _is_upstream(graph, request.target_node_id, request.source_node_id):
        return APIResponse(
            success=True,
            data=ConnectionValidation(
                is_valid=False,
                source_type=source_type,
                target_type=target_type,
                warning="This connection would create a cycle",
                suggestion="Use a Loop node for intentional iteration"
            )
        )

    return APIResponse(
        success=True,
        data=ConnectionValidation(
            is_valid=is_compatible,
            source_type=source_type,
            target_type=target_type,
            warning=warning,
            suggestion=suggestion
        )
    )


# CONVENIENCE ENDPOINT

@router.get(
    "/syntax-help",
    response_model=APIResponse[SyntaxHelp],
    summary="Get variable syntax help",
    description="Returns documentation for variable syntax"
)
async def get_syntax_help():
    """Returns variable syntax documentation."""
    return APIResponse(
        success=True,
        message="Variable syntax reference",
        data=SyntaxHelp()
    )