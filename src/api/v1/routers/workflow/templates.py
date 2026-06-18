"""
Templates API - Unified entry point for all three data flow methods.

This module provides the backend infrastructure for:
1. Visual Data Flow (connect dots) - Auto-generates Jinja2 from edge mappings
2. Variable Picker (click to insert) - Generates proper Jinja2 syntax
3. Manual Jinja2 Syntax - Validation and preview

All three methods ultimately generate the same underlying Jinja2 template,
just with different UX entry points.
"""

from typing import List, Dict, Any, Optional, Set
from uuid import UUID
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.workflow import Workflow
from src.dao.workflow_dao import WorkflowDAO
from src.services.workflow_engine.registry import NodeRegistry
from src.schemas.workflow.response import APIResponse


router = APIRouter(prefix="/templates", tags=["Templates"])


# ============================================================
# SCHEMAS
# ============================================================

class VariableInsertFormat(str, Enum):
    """Format for variable insertion."""
    FULL = "full"           # {{ steps['node-id'].field }}
    SHORTHAND = "shorthand"  # {{ NodeLabel.field }}
    RAW = "raw"             # steps['node-id'].field (no braces)


class TemplateValidationRequest(BaseModel):
    """Request to validate a Jinja2 template."""
    template: str = Field(..., description="Template string to validate")
    context_sample: Optional[Dict[str, Any]] = Field(
        None,
        description="Sample context for rendering test"
    )


class TemplateError(BaseModel):
    """Details about a template error."""
    type: str = Field(..., description="Error type: syntax, undefined, runtime")
    message: str = Field(..., description="Error message")
    line: Optional[int] = Field(None, description="Line number if available")
    column: Optional[int] = Field(None, description="Column number if available")
    suggestion: Optional[str] = Field(None, description="Suggested fix")


class TemplateValidationResponse(BaseModel):
    """Response from template validation."""
    is_valid: bool
    errors: List[TemplateError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    variables_used: List[str] = Field(default_factory=list)
    rendered_preview: Optional[str] = None


class VariableInsertRequest(BaseModel):
    """Request to generate a variable insertion template."""
    node_id: str = Field(..., description="Source node ID")
    field_path: str = Field(..., description="Field path (dot notation)")
    format: VariableInsertFormat = Field(
        default=VariableInsertFormat.FULL,
        description="Output format"
    )
    filters: List[str] = Field(
        default_factory=list,
        description="Jinja2 filters to apply (e.g., ['trim', 'upper'])"
    )
    default_value: Optional[str] = Field(
        None,
        description="Default value if field is undefined"
    )


class VariableInsertResponse(BaseModel):
    """Response with generated template syntax."""
    template: str = Field(..., description="Generated Jinja2 template")
    full_syntax: str = Field(..., description="Full steps['id'].field syntax")
    shorthand_syntax: Optional[str] = Field(None, description="Shorthand syntax if available")
    raw_path: str = Field(..., description="Raw path without braces")


class EdgeMappingRequest(BaseModel):
    """Request to generate Jinja2 from visual edge connection."""
    source_node_id: str
    source_handle: str = "output"
    target_node_id: str
    target_handle: str = "input"
    field_mappings: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of {source_field, target_field, transform?}"
    )


class EdgeMappingResponse(BaseModel):
    """Response with generated templates from edge mapping."""
    templates: Dict[str, str] = Field(
        ...,
        description="Map of target_field -> Jinja2 template"
    )
    auto_mappings: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Suggested auto-mappings based on field names"
    )


class TemplatePreviewRequest(BaseModel):
    """Request to preview template rendering."""
    template: str = Field(..., description="Template to render")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Context data for rendering"
    )
    strict: bool = Field(
        default=False,
        description="Raise errors for undefined variables"
    )


class TemplatePreviewResponse(BaseModel):
    """Response from template preview."""
    success: bool
    rendered: Optional[str] = None
    error: Optional[TemplateError] = None
    execution_time_ms: float = 0


class AvailableFilter(BaseModel):
    """Documentation for an available Jinja2 filter."""
    name: str
    description: str
    example: str
    category: str


class SyntaxReference(BaseModel):
    """Complete syntax reference for templates."""
    variable_formats: Dict[str, str]
    special_variables: Dict[str, str]
    available_filters: List[AvailableFilter]
    examples: List[Dict[str, str]]


# ============================================================
# HELPERS
# ============================================================

class SilentUndefined:
    """Custom Undefined that tracks usage but returns empty string."""

    def __init__(self, name=None):
        self.name = name
        self._accessed_vars = set()

    def __str__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __getattr__(self, name):
        return SilentUndefined(f"{self.name}.{name}" if self.name else name)


def _create_secure_env() -> SandboxedEnvironment:
    """Creates a sandboxed Jinja2 environment with custom filters."""
    env = SandboxedEnvironment(loader=BaseLoader(), autoescape=False)

    # Add safe filters
    env.filters['default'] = lambda v, d="": v if v else d
    env.filters['trim'] = lambda v: v.strip() if isinstance(v, str) else v
    env.filters['upper'] = lambda v: v.upper() if isinstance(v, str) else v
    env.filters['lower'] = lambda v: v.lower() if isinstance(v, str) else v
    env.filters['title'] = lambda v: v.title() if isinstance(v, str) else v
    env.filters['int'] = lambda v, d=0: int(v) if str(v).isdigit() else d
    env.filters['float'] = lambda v, d=0.0: float(v) if v else d
    env.filters['json'] = lambda v: __import__('json').dumps(v)
    env.filters['first'] = lambda v: v[0] if isinstance(v, (list, tuple)) and v else None
    env.filters['last'] = lambda v: v[-1] if isinstance(v, (list, tuple)) and v else None
    env.filters['join'] = lambda v, d=", ": d.join(str(x) for x in v) if isinstance(v, list) else v
    env.filters['length'] = lambda v: len(v) if hasattr(v, '__len__') else 0
    env.filters['keys'] = lambda v: list(v.keys()) if isinstance(v, dict) else []
    env.filters['values'] = lambda v: list(v.values()) if isinstance(v, dict) else []
    env.filters['replace'] = lambda v, old, new: v.replace(old, new) if isinstance(v, str) else v
    env.filters['split'] = lambda v, d=" ": v.split(d) if isinstance(v, str) else v

    return env


def _extract_variables(template: str) -> List[str]:
    """Extracts variable references from a template."""
    import re
    # Match {{ variable.path }} patterns
    pattern = r'\{\{\s*([^}|]+?)(?:\s*\||\s*\}\})'
    matches = re.findall(pattern, template)

    variables = []
    for match in matches:
        var = match.strip()
        # Clean up steps['node-id'].field to just the path
        if var.startswith("steps["):
            variables.append(var)
        elif "." in var:
            variables.append(var)
        else:
            variables.append(var)

    return list(set(variables))


def _get_node_label(workflow: Workflow, node_id: str) -> Optional[str]:
    """Gets the label for a node."""
    graph = workflow.graph_definition
    for node in graph.get("nodes", []):
        if node["id"] == node_id:
            return node.get("data", {}).get("label", node_id)
    return None


def _suggest_fix(error_msg: str, template: str) -> Optional[str]:
    """Suggests a fix for common template errors."""
    error_lower = error_msg.lower()

    if "unexpected end of template" in error_lower:
        return "Check for unclosed {{ or {% tags"
    if "expected token 'end of print statement'" in error_lower:
        return "Check for missing }} at the end of the expression"
    if "undefined" in error_lower:
        import re
        match = re.search(r"'(\w+)' is undefined", error_msg)
        if match:
            var_name = match.group(1)
            return f"Variable '{var_name}' doesn't exist. Use the Variable Picker to see available variables."
    if "no filter named" in error_lower:
        import re
        match = re.search(r"no filter named '(\w+)'", error_lower)
        if match:
            filter_name = match.group(1)
            return f"Filter '{filter_name}' is not available. Check /templates/reference for available filters."

    return None


def _get_available_filters() -> List[AvailableFilter]:
    """Returns documentation for all available filters."""
    return [
        AvailableFilter(
            name="default",
            description="Return a default value if the variable is undefined or empty",
            example="{{ value | default('fallback') }}",
            category="defaults"
        ),
        AvailableFilter(
            name="trim",
            description="Remove leading and trailing whitespace",
            example="{{ text | trim }}",
            category="string"
        ),
        AvailableFilter(
            name="upper",
            description="Convert to uppercase",
            example="{{ text | upper }}",
            category="string"
        ),
        AvailableFilter(
            name="lower",
            description="Convert to lowercase",
            example="{{ text | lower }}",
            category="string"
        ),
        AvailableFilter(
            name="title",
            description="Convert to title case",
            example="{{ text | title }}",
            category="string"
        ),
        AvailableFilter(
            name="replace",
            description="Replace occurrences of a substring",
            example="{{ text | replace('old', 'new') }}",
            category="string"
        ),
        AvailableFilter(
            name="split",
            description="Split a string into a list",
            example="{{ text | split(',') }}",
            category="string"
        ),
        AvailableFilter(
            name="int",
            description="Convert to integer",
            example="{{ value | int }}",
            category="type"
        ),
        AvailableFilter(
            name="float",
            description="Convert to float",
            example="{{ value | float }}",
            category="type"
        ),
        AvailableFilter(
            name="json",
            description="Convert to JSON string",
            example="{{ data | json }}",
            category="type"
        ),
        AvailableFilter(
            name="first",
            description="Get first item of array",
            example="{{ items | first }}",
            category="array"
        ),
        AvailableFilter(
            name="last",
            description="Get last item of array",
            example="{{ items | last }}",
            category="array"
        ),
        AvailableFilter(
            name="join",
            description="Join array elements with separator",
            example="{{ items | join(', ') }}",
            category="array"
        ),
        AvailableFilter(
            name="length",
            description="Get length of array or string",
            example="{{ items | length }}",
            category="array"
        ),
        AvailableFilter(
            name="keys",
            description="Get dictionary keys as list",
            example="{{ data | keys }}",
            category="object"
        ),
        AvailableFilter(
            name="values",
            description="Get dictionary values as list",
            example="{{ data | values }}",
            category="object"
        ),
    ]


# ============================================================
# ENDPOINTS
# ============================================================

@router.post(
    "/validate",
    response_model=APIResponse[TemplateValidationResponse],
    summary="Validate a Jinja2 template",
    description="Pre-flight validation of template syntax before save/execution"
)
async def validate_template(
        request: TemplateValidationRequest,
        current_user: User = Depends(get_current_user)
):
    """
    Validates a Jinja2 template for syntax errors.

    This is the key endpoint for the Manual Jinja2 Syntax method,
    enabling developers to get immediate feedback on their templates.

    Returns:
        - is_valid: Whether the template is syntactically correct
        - errors: List of errors with line numbers and suggestions
        - warnings: Non-fatal issues
        - variables_used: List of variables referenced in the template
        - rendered_preview: Preview if sample context provided
    """
    errors: List[TemplateError] = []
    warnings: List[str] = []
    rendered_preview = None

    env = _create_secure_env()

    # Step 1: Syntax validation
    try:
        template = env.from_string(request.template)
    except TemplateSyntaxError as e:
        errors.append(TemplateError(
            type="syntax",
            message=str(e),
            line=e.lineno,
            suggestion=_suggest_fix(str(e), request.template)
        ))
        return APIResponse(
            success=True,
            data=TemplateValidationResponse(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                variables_used=[]
            )
        )

    # Step 2: Extract variables
    variables_used = _extract_variables(request.template)

    # Step 3: Try rendering with sample context
    if request.context_sample:
        try:
            context = {
                "steps": request.context_sample.get("steps", {}),
                "item": request.context_sample.get("item"),
                "env": request.context_sample.get("env", {})
            }
            rendered_preview = template.render(**context)
        except UndefinedError as e:
            warnings.append(f"Some variables are undefined: {e}")
        except Exception as e:
            errors.append(TemplateError(
                type="runtime",
                message=str(e),
                suggestion=_suggest_fix(str(e), request.template)
            ))

    # Step 4: Additional validations
    if "{{" in request.template and "}}" not in request.template:
        warnings.append("Template may have unclosed {{ tag")

    if "{%" in request.template and "%}" not in request.template:
        warnings.append("Template may have unclosed {% tag")

    return APIResponse(
        success=True,
        message="Template validation complete",
        data=TemplateValidationResponse(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            variables_used=variables_used,
            rendered_preview=rendered_preview
        )
    )


@router.post(
    "/workflows/{workflow_id}/insert-variable",
    response_model=APIResponse[VariableInsertResponse],
    summary="Generate Jinja2 syntax for variable insertion",
    description="Click-to-insert variable picker generates proper Jinja2"
)
async def insert_variable(
        workflow_id: UUID,
        request: VariableInsertRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Generates Jinja2 template syntax for inserting a variable.

    This is the key endpoint for the Variable Picker (click to insert) method.
    Power users click on a variable in the picker, and this endpoint generates
    the proper Jinja2 syntax to insert into their text field.

    Supports:
        - Full format: {{ steps['node-id'].field }}
        - Shorthand format: {{ NodeLabel.field }}
        - With filters: {{ steps['node-id'].field | trim | upper }}
        - With default: {{ steps['node-id'].field | default('fallback') }}
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
            detail="Not authorized"
        )

    # Validate node exists
    node_label = _get_node_label(workflow, request.node_id)
    if not node_label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Node '{request.node_id}' not found in workflow"
        )

    # Build paths
    raw_path = f"steps['{request.node_id}'].{request.field_path}"
    clean_label = node_label.replace(" ", "").replace("-", "_")
    shorthand_path = f"{clean_label}.{request.field_path}"

    # Build filter chain
    filter_chain = ""
    if request.filters:
        filter_chain = " | " + " | ".join(request.filters)
    if request.default_value:
        filter_chain += f" | default('{request.default_value}')"

    # Generate templates
    full_syntax = f"{{{{ {raw_path}{filter_chain} }}}}"
    shorthand_syntax = f"{{{{ {shorthand_path}{filter_chain} }}}}"

    # Select output based on format
    if request.format == VariableInsertFormat.FULL:
        template = full_syntax
    elif request.format == VariableInsertFormat.SHORTHAND:
        template = shorthand_syntax
    else:  # RAW
        template = raw_path

    return APIResponse(
        success=True,
        message="Variable template generated",
        data=VariableInsertResponse(
            template=template,
            full_syntax=full_syntax,
            shorthand_syntax=shorthand_syntax,
            raw_path=raw_path
        )
    )


@router.post(
    "/workflows/{workflow_id}/edge-to-template",
    response_model=APIResponse[EdgeMappingResponse],
    summary="Generate Jinja2 from visual edge connection",
    description="Converts visual data flow connections to Jinja2 templates"
)
async def edge_to_template(
        workflow_id: UUID,
        request: EdgeMappingRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Generates Jinja2 templates from visual edge connections.

    This is the key endpoint for the Visual Data Flow method.
    When a user draws a connection between nodes and maps fields,
    this endpoint generates the underlying Jinja2 that makes it work.

    Example:
        User connects Search → AI node visually
        Maps: answer → context, citations[0] → source

        Generates:
        {
            "context": "{{ steps['search-1'].answer }}",
            "source": "{{ steps['search-1'].citations[0] }}"
        }
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
            detail="Not authorized"
        )

    # Validate source node exists
    source_label = _get_node_label(workflow, request.source_node_id)
    if not source_label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source node '{request.source_node_id}' not found"
        )

    templates = {}
    auto_mappings = []

    # Process explicit field mappings
    if request.field_mappings:
        for mapping in request.field_mappings:
            source_field = mapping.get("source_field", "output")
            target_field = mapping.get("target_field", "input")
            transform = mapping.get("transform")

            template = f"{{{{ steps['{request.source_node_id}'].{source_field}"

            if transform:
                template += f" | {transform}"

            template += " }}"
            templates[target_field] = template
    else:
        # Default mapping: sourceHandle → targetHandle
        templates[request.target_handle] = (
            f"{{{{ steps['{request.source_node_id}'].{request.source_handle} }}}}"
        )

    # Generate auto-mapping suggestions
    try:
        source_node_type = None
        target_node_type = None
        graph = workflow.graph_definition

        for node in graph.get("nodes", []):
            if node["id"] == request.source_node_id:
                source_node_type = node.get("type")
            if node["id"] == request.target_node_id:
                target_node_type = node.get("type")

        if source_node_type and target_node_type:
            # Get source outputs
            try:
                source_class = NodeRegistry.get_node(source_node_type)
                source_manifest = source_class.get_manifest()
                source_outputs = source_manifest.get("outputs", ["output"])
            except Exception:
                source_outputs = ["output"]

            # Get target inputs
            try:
                target_class = NodeRegistry.get_node(target_node_type)
                target_manifest = target_class.get_manifest()
                target_fields = [
                    f.get("name") for f in target_manifest.get("fields", [])
                ]
            except Exception:
                target_fields = ["input"]

            # Suggest mappings for matching names
            for output in source_outputs:
                for field in target_fields:
                    if output.lower() == field.lower():
                        auto_mappings.append({
                            "source_field": output,
                            "target_field": field,
                            "confidence": "high"
                        })
                    elif output in field or field in output:
                        auto_mappings.append({
                            "source_field": output,
                            "target_field": field,
                            "confidence": "medium"
                        })

    except Exception as e:
        logger.debug(f"Auto-mapping failed: {e}")

    return APIResponse(
        success=True,
        message="Edge converted to templates",
        data=EdgeMappingResponse(
            templates=templates,
            auto_mappings=auto_mappings
        )
    )


@router.post(
    "/preview",
    response_model=APIResponse[TemplatePreviewResponse],
    summary="Preview template rendering",
    description="Test a template with sample data"
)
async def preview_template(
        request: TemplatePreviewRequest,
        current_user: User = Depends(get_current_user)
):
    """
    Renders a template with provided context for testing.

    This endpoint enables developers to test their Jinja2 templates
    before committing them, seeing exactly what the output will be.
    """
    import time

    env = _create_secure_env()
    start_time = time.perf_counter()

    try:
        template = env.from_string(request.template)
        rendered = template.render(**request.context)
        execution_time = (time.perf_counter() - start_time) * 1000

        return APIResponse(
            success=True,
            message="Template rendered successfully",
            data=TemplatePreviewResponse(
                success=True,
                rendered=rendered,
                execution_time_ms=round(execution_time, 2)
            )
        )

    except TemplateSyntaxError as e:
        return APIResponse(
            success=True,
            data=TemplatePreviewResponse(
                success=False,
                error=TemplateError(
                    type="syntax",
                    message=str(e),
                    line=e.lineno,
                    suggestion=_suggest_fix(str(e), request.template)
                ),
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2)
            )
        )

    except UndefinedError as e:
        return APIResponse(
            success=True,
            data=TemplatePreviewResponse(
                success=False,
                error=TemplateError(
                    type="undefined",
                    message=str(e),
                    suggestion=_suggest_fix(str(e), request.template)
                ),
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2)
            )
        )

    except Exception as e:
        return APIResponse(
            success=True,
            data=TemplatePreviewResponse(
                success=False,
                error=TemplateError(
                    type="runtime",
                    message=str(e),
                    suggestion=_suggest_fix(str(e), request.template)
                ),
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2)
            )
        )


@router.get(
    "/reference",
    response_model=APIResponse[SyntaxReference],
    summary="Get template syntax reference",
    description="Complete documentation for template syntax and filters"
)
async def get_syntax_reference():
    """
    Returns complete syntax reference for templates.

    Documents all three data flow methods:
    1. Visual Data Flow - auto-generated from connections
    2. Variable Picker - click-to-insert syntax
    3. Manual Jinja2 - full syntax documentation
    """
    return APIResponse(
        success=True,
        message="Template syntax reference",
        data=SyntaxReference(
            variable_formats={
                "full": "{{ steps['node-id'].field }}",
                "shorthand": "{{ NodeLabel.field }}",
                "previous": "{{ @previous.output }}",
                "loop_item": "{{ item }}",
                "loop_index": "{{ loop.index }}",
                "global": "{{ env.variable_name }}",
                "nested": "{{ steps['node-id'].data.nested.field }}"
            },
            special_variables={
                "@previous": "References the immediately preceding node's output",
                "item": "Current item in a loop iteration",
                "loop.index": "Current iteration number (1-based)",
                "loop.index0": "Current iteration number (0-based)",
                "loop.first": "True if first iteration",
                "loop.last": "True if last iteration",
                "env": "Global workflow variables",
                "now": "Current timestamp"
            },
            available_filters=_get_available_filters(),
            examples=[
                {
                    "name": "Simple Variable",
                    "description": "Reference a node's output",
                    "template": "{{ steps['webhook-1'].response }}"
                },
                {
                    "name": "With Shorthand",
                    "description": "Use node label instead of ID",
                    "template": "{{ FetchData.response }}"
                },
                {
                    "name": "With Filter",
                    "description": "Apply transformation",
                    "template": "{{ steps['ai-1'].answer | trim | upper }}"
                },
                {
                    "name": "With Default",
                    "description": "Provide fallback value",
                    "template": "{{ steps['search-1'].result | default('No results') }}"
                },
                {
                    "name": "Nested Field",
                    "description": "Access nested object properties",
                    "template": "{{ steps['api-1'].data.users[0].name }}"
                },
                {
                    "name": "Previous Node",
                    "description": "Reference the previous node",
                    "template": "{{ @previous.output }}"
                },
                {
                    "name": "Loop Item",
                    "description": "Access current loop item",
                    "template": "Processing: {{ item.name }} ({{ loop.index }}/{{ loop.length }})"
                },
                {
                    "name": "Conditional",
                    "description": "Conditional logic in template",
                    "template": "{% if steps['search-1'].results %}Found {{ steps['search-1'].results | length }} results{% else %}No results{% endif %}"
                },
                {
                    "name": "Join Array",
                    "description": "Join array elements",
                    "template": "Tags: {{ steps['fetch-1'].tags | join(', ') }}"
                },
                {
                    "name": "JSON Output",
                    "description": "Output as JSON string",
                    "template": "Data: {{ steps['api-1'].response | json }}"
                }
            ]
        )
    )


@router.post(
    "/workflows/{workflow_id}/expand-fields",
    response_model=APIResponse[Dict[str, Any]],
    summary="Expand nested fields for a variable",
    description="Dynamically expand object/array fields for the variable picker"
)
async def expand_variable_fields(
        workflow_id: UUID,
        node_id: str = Query(..., description="Node to expand fields for"),
        field_path: str = Query("", description="Base path to expand from"),
        execution_id: Optional[UUID] = Query(None, description="Use actual execution data if available"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Expands nested fields for the Variable Picker.

    When a user clicks to expand an object or array field, this endpoint
    returns the available nested fields with their types.

    Can use:
    - Schema from node manifest (static, always available)
    - Actual execution data (dynamic, if execution_id provided)
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

    # Find the node
    graph = workflow.graph_definition
    node = None
    for n in graph.get("nodes", []):
        if n["id"] == node_id:
            node = n
            break

    if not node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Node '{node_id}' not found"
        )

    node_type = node.get("type")
    fields = []

    # Try to get schema from manifest
    try:
        node_class = NodeRegistry.get_node(node_type)
        manifest = node_class.get_manifest()
        outputs_schema = manifest.get("outputs_schema", {})

        # Navigate to the field_path in schema
        current_schema = outputs_schema
        if field_path:
            parts = field_path.split(".")
            for part in parts:
                if isinstance(current_schema, dict):
                    if "properties" in current_schema:
                        current_schema = current_schema.get("properties", {}).get(part, {})
                    else:
                        current_schema = current_schema.get(part, {})

        # Extract fields from schema
        if isinstance(current_schema, dict):
            if "properties" in current_schema:
                for name, schema in current_schema["properties"].items():
                    field_type = schema.get("type", "any")
                    full_path = f"{field_path}.{name}" if field_path else name
                    fields.append({
                        "name": name,
                        "path": full_path,
                        "type": field_type,
                        "expandable": field_type in ["object", "array"],
                        "description": schema.get("description")
                    })
            elif "items" in current_schema:
                # Array type - show item fields
                item_schema = current_schema["items"]
                if "properties" in item_schema:
                    for name, schema in item_schema["properties"].items():
                        full_path = f"{field_path}[*].{name}" if field_path else f"[*].{name}"
                        fields.append({
                            "name": f"[item].{name}",
                            "path": full_path,
                            "type": schema.get("type", "any"),
                            "expandable": schema.get("type") in ["object", "array"],
                            "description": schema.get("description")
                        })

    except Exception as e:
        logger.debug(f"Could not get schema for {node_type}: {e}")

    # TODO: If execution_id provided, fetch actual data from execution
    # and infer fields from actual response structure

    return APIResponse(
        success=True,
        message=f"Found {len(fields)} expandable fields",
        data={
            "node_id": node_id,
            "base_path": field_path,
            "fields": fields
        }
    )
