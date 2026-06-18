import importlib
import pkgutil
import inspect
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from fastapi import APIRouter, Query, HTTPException, status, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext
from src.services.workflow_engine.registry import NodeRegistry
from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.models.sql.workflow.connection import Connection
from src.core.security import decrypt_credentials
from src.schemas.workflow.response import APIResponse


# ============================================================
# CONFIGURATION
# ============================================================

CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_TIMESTAMP: Optional[datetime] = None
CACHED_MANIFESTS: List[Dict[str, Any]] = []


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# DISCOVERY FUNCTIONS
# ============================================================

def discover_node_manifests(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Discovers and caches node manifests.

    Features:
    - In-memory caching with TTL
    - Duplicate detection
    - Error isolation
    - Sorted output

    Args:
        force_refresh: Force cache refresh

    Returns:
        List of node manifests
    """
    global CACHE_TIMESTAMP, CACHED_MANIFESTS

    # Check cache
    if not force_refresh and CACHE_TIMESTAMP:
        if datetime.now(timezone.utc) - CACHE_TIMESTAMP < timedelta(seconds=CACHE_TTL_SECONDS):
            return CACHED_MANIFESTS

    manifests = []
    processed_classes = set()
    errors = []

    try:
        # Import nodes package
        import app.services.workflow_engine.nodes as nodes_package

        package_path = nodes_package.__path__
        prefix = nodes_package.__name__ + "."

        # Walk through all modules
        for loader, module_name, is_pkg in pkgutil.walk_packages(package_path, prefix):
            try:
                # Import module
                module = importlib.import_module(module_name)

                # Find BaseNode subclasses
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseNode) and obj is not BaseNode:
                        if obj in processed_classes:
                            continue

                        try:
                            # Extract manifest
                            manifest = obj.get_manifest()

                            # Validate manifest
                            validated = _validate_manifest(manifest, obj.node_type)
                            if validated:
                                manifests.append(validated)
                                processed_classes.add(obj)

                        except AttributeError:
                            logger.warning(
                                f"Node class {name} missing get_manifest()",
                                extra={"class": name, "module": module_name}
                            )
                        except Exception as e:
                            logger.error(
                                f"Error extracting manifest from {name}: {e}",
                                extra={"class": name, "error": str(e)}
                            )
                            errors.append(f"{name}: {str(e)}")

            except Exception as e:
                logger.error(
                    f"Failed to import module {module_name}: {e}",
                    extra={"module": module_name, "error": str(e)}
                )
                errors.append(f"Module {module_name}: {str(e)}")

        # Sort by category and name
        manifests.sort(key=lambda x: (
            x.get("category", "Other"),
            x.get("display_name", x.get("type", ""))
        ))

        # Update cache
        CACHED_MANIFESTS = manifests
        CACHE_TIMESTAMP = datetime.now(timezone.utc)

        if errors:
            logger.warning(f"Node discovery completed with {len(errors)} errors")
        else:
            logger.info(f"Discovered {len(manifests)} nodes")

        return manifests

    except ImportError as e:
        logger.error(f"Failed to import nodes package: {e}")
        return []


def _validate_manifest(
        manifest: Dict[str, Any],
        node_type: str
) -> Optional[Dict[str, Any]]:
    """
    Validates and normalizes a node manifest.

    Args:
        manifest: Raw manifest dictionary
        node_type: Node type string

    Returns:
        Validated manifest or None
    """
    if not manifest:
        return None

    if not isinstance(manifest, dict):
        return None

    # Ensure required fields
    validated = {
        "type": manifest.get("type", node_type),
        "display_name": manifest.get("display_name", node_type.replace("Node", "")),
        "icon": manifest.get("icon", "Box"),
        "category": manifest.get("category", "Other"),
        "description": manifest.get("description", ""),
        "fields": [],
        "outputs": manifest.get("outputs", ["success"]),
    }

    # Validate fields
    for field in manifest.get("fields", []):
        if not isinstance(field, dict):
            continue

        validated_field = {
            "name": field.get("name", ""),
            "label": field.get("label", field.get("name", "")),
            "type": field.get("type", "text"),
            "required": field.get("required", False),
            "default": field.get("default"),
            "placeholder": field.get("placeholder", ""),
            "description": field.get("description", ""),
            "options": field.get("options"),
            "conditional": field.get("conditional"),
        }

        # Remove None values
        validated_field = {k: v for k, v in validated_field.items() if v is not None}

        if validated_field.get("name"):
            validated["fields"].append(validated_field)

    return validated


# ============================================================
# ENDPOINTS
# ============================================================

@router.get(
    "/registry",
    response_model=APIResponse,
    summary="Get node registry",
    description="Returns all available node types with their configurations"
)
async def get_node_registry(
        refresh: bool = Query(False, description="Force cache refresh")
):
    """
    Node registry discovery endpoint.

    Returns all registered node types with their:
    - Display information
    - Configuration fields
    - Output handles
    """
    try:
        nodes = discover_node_manifests(force_refresh=refresh)

        return APIResponse(
            success=True,
            message=f"Found {len(nodes)} registered nodes",
            data={
                "count": len(nodes),
                "nodes": nodes
            },
            meta={
                "cached": not refresh,
                "cache_ttl": CACHE_TTL_SECONDS
            }
        )

    except Exception as e:
        logger.error(f"Node registry error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load node registry: {str(e)}"
        )


@router.get(
    "/registry/categories",
    response_model=APIResponse,
    summary="Get node categories",
    description="Returns nodes grouped by category"
)
async def get_node_categories():
    """
    Returns nodes organized by category.
    """
    nodes = discover_node_manifests()

    categories: Dict[str, List[Dict[str, Any]]] = {}

    for node in nodes:
        category = node.get("category", "Other")
        if category not in categories:
            categories[category] = []
        categories[category].append(node)

    return APIResponse(
        success=True,
        message=f"Found {len(categories)} categories",
        data={
            "categories": categories,
            "category_names": sorted(categories.keys())
        }
    )


@router.get(
    "/registry/search",
    response_model=APIResponse,
    summary="Search nodes",
    description="Search for nodes by name or description"
)
async def search_nodes(
        q: str = Query(..., min_length=2, description="Search query"),
        category: Optional[str] = Query(None, description="Filter by category")
):
    """
    Searches nodes by name or description.
    """
    nodes = discover_node_manifests()
    query = q.lower()

    results = []
    for node in nodes:
        # Filter by category if specified
        if category and node.get("category") != category:
            continue

        # Search in name, description, and type
        searchable = " ".join([
            node.get("display_name", ""),
            node.get("description", ""),
            node.get("type", "")
        ]).lower()

        if query in searchable:
            results.append(node)

    return APIResponse(
        success=True,
        message=f"Found {len(results)} matching nodes",
        data={
            "query": q,
            "count": len(results),
            "nodes": results
        }
    )


@router.get(
    "/registry/{node_type}",
    response_model=APIResponse,
    summary="Get node details",
    description="Returns detailed information about a specific node type"
)
async def get_node_details(node_type: str):
    """
    Returns detailed manifest for a specific node type.
    """
    nodes = discover_node_manifests()

    for node in nodes:
        if node.get("type") == node_type:
            return APIResponse(
                success=True,
                message=f"Found node: {node_type}",
                data=node
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Node type '{node_type}' not found"
    )


@router.get(
    "/registry/{node_type}/schema",
    response_model=APIResponse,
    summary="Get node input schema",
    description="Returns JSON schema for node inputs"
)
async def get_node_schema(node_type: str):
    """
    Returns JSON schema for node configuration.

    Useful for form generation and validation.
    """
    nodes = discover_node_manifests()

    for node in nodes:
        if node.get("type") == node_type:
            # Build JSON schema from fields
            schema = _build_json_schema(node)

            return APIResponse(
                success=True,
                message=f"Schema for {node_type}",
                data=schema
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Node type '{node_type}' not found"
    )


def _build_json_schema(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Builds JSON schema from manifest fields."""
    properties = {}
    required = []

    type_mapping = {
        "text": "string",
        "textarea": "string",
        "number": "number",
        "boolean": "boolean",
        "select": "string",
        "json_editor": "object",
        "code_editor": "string",
        "password": "string",
        "connection_select": "string",
        "list": "array",
    }

    for field in manifest.get("fields", []):
        field_name = field.get("name")
        field_type = field.get("type", "text")

        prop = {
            "type": type_mapping.get(field_type, "string"),
            "title": field.get("label", field_name),
            "description": field.get("description", ""),
        }

        if field.get("default") is not None:
            prop["default"] = field.get("default")

        if field.get("options"):
            prop["enum"] = field.get("options")

        if field.get("placeholder"):
            prop["examples"] = [field.get("placeholder")]

        properties[field_name] = prop

        if field.get("required"):
            required.append(field_name)

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "title": manifest.get("display_name", ""),
        "description": manifest.get("description", ""),
        "properties": properties,
        "required": required,
    }


# ============================================================
# SINGLE NODE TEST ENDPOINT
# ============================================================

class NodeTestRequest(BaseModel):
    """Request schema for testing a single node."""
    node_type: str = Field(
        ...,
        description="The type of node to test (e.g., 'slackNode', 'gmailNode')"
    )
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input data to pass to the node"
    )
    connection_id: Optional[str] = Field(
        default=None,
        description="Optional connection ID for nodes requiring credentials"
    )
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Maximum execution time in seconds"
    )


class NodeTestResponse(BaseModel):
    """Response schema for single node test."""
    success: bool
    node_type: str
    duration_ms: int
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


@router.post(
    "/test",
    response_model=APIResponse[NodeTestResponse],
    summary="Test single node",
    description="Execute a single node in isolation without creating a full workflow execution"
)
async def test_single_node(
    body: NodeTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Tests a single node in isolation.

    This endpoint allows developers to test individual nodes without
    creating a full workflow execution. Useful for:
    - Validating node configurations
    - Testing connection credentials
    - Debugging node behavior
    - API integration testing

    Security:
    - Requires authentication
    - Only uses connections owned by the user
    - Execution is sandboxed with timeout
    """
    start_time = datetime.now(timezone.utc)

    # Validate node type exists
    if not NodeRegistry.has_node(body.node_type):
        available_nodes = NodeRegistry.list_nodes()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"Unknown node type: {body.node_type}",
                "available_nodes": sorted(available_nodes)[:20]  # Limit for response size
            }
        )

    try:
        # Get node instance
        node = NodeRegistry.get_node(body.node_type)

        # Build mock execution context
        test_execution_id = str(uuid.uuid4())
        context = ExecutionContext(
            workflow_id="test-workflow",
            execution_id=test_execution_id,
            user_id=current_user.id,
            node_outputs={},
            connections={}
        )

        # If connection_id provided, fetch and cache credentials
        if body.connection_id:
            from sqlalchemy import select
            query = select(Connection).where(
                Connection.id == body.connection_id,
                Connection.user_id == current_user.id
            )
            result = await db.execute(query)
            connection = result.scalar_one_or_none()

            if not connection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Connection not found or not authorized"
                )

            # Decrypt and cache credentials
            try:
                decrypted = decrypt_credentials(connection.encrypted_credentials)
                context.connections[body.connection_id] = decrypted
            except Exception as e:
                logger.error(f"Failed to decrypt connection credentials: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to decrypt connection credentials"
                )

        # Prepare input data - inject connection_id if present
        input_data = body.input_data.copy()
        if body.connection_id and "connection_id" not in input_data:
            input_data["connection_id"] = body.connection_id

        # Execute with timeout
        try:
            output = await asyncio.wait_for(
                node.execute(db, context, input_data),
                timeout=body.timeout_seconds
            )

            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            logger.info(
                f"Single node test completed: {body.node_type}",
                extra={
                    "user_id": str(current_user.id),
                    "node_type": body.node_type,
                    "duration_ms": duration_ms,
                    "success": True
                }
            )

            return APIResponse(
                success=True,
                message="Node executed successfully",
                data=NodeTestResponse(
                    success=True,
                    node_type=body.node_type,
                    duration_ms=duration_ms,
                    output=output
                )
            )

        except asyncio.TimeoutError:
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            logger.warning(
                f"Single node test timed out: {body.node_type}",
                extra={
                    "user_id": str(current_user.id),
                    "node_type": body.node_type,
                    "timeout_seconds": body.timeout_seconds
                }
            )

            return APIResponse(
                success=True,
                message="Node execution timed out",
                data=NodeTestResponse(
                    success=False,
                    node_type=body.node_type,
                    duration_ms=duration_ms,
                    error=f"Execution timed out after {body.timeout_seconds} seconds",
                    error_details={"timeout_seconds": body.timeout_seconds}
                )
            )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        logger.error(
            f"Single node test failed: {body.node_type} - {str(e)}",
            extra={
                "user_id": str(current_user.id),
                "node_type": body.node_type,
                "error": str(e)
            }
        )

        return APIResponse(
            success=True,
            message="Node execution failed",
            data=NodeTestResponse(
                success=False,
                node_type=body.node_type,
                duration_ms=duration_ms,
                error=str(e),
                error_details={
                    "error_type": type(e).__name__,
                    "message": str(e)
                }
            )
        )


@router.get(
    "/test/validate/{node_type}",
    response_model=APIResponse,
    summary="Validate node configuration",
    description="Validate node input configuration without executing"
)
async def validate_node_config(
    node_type: str,
    current_user: User = Depends(get_current_user)
):
    """
    Validates that a node type exists and returns its required fields.

    Useful for frontend form validation before attempting execution.
    """
    if not NodeRegistry.has_node(node_type):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node type '{node_type}' not found"
        )

    manifest = NodeRegistry.get_manifest(node_type)

    # Extract required fields
    required_fields = []
    optional_fields = []

    for field in manifest.get("fields", []):
        field_info = {
            "name": field.get("name"),
            "label": field.get("label"),
            "type": field.get("type"),
            "description": field.get("description", ""),
            "default": field.get("default")
        }

        if field.get("required"):
            required_fields.append(field_info)
        else:
            optional_fields.append(field_info)

    # Check if node requires a connection
    requires_connection = any(
        f.get("type") == "connection_select"
        for f in manifest.get("fields", [])
    )

    return APIResponse(
        success=True,
        message=f"Validation info for {node_type}",
        data={
            "node_type": node_type,
            "display_name": manifest.get("display_name"),
            "category": manifest.get("category"),
            "requires_connection": requires_connection,
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "outputs": manifest.get("outputs", [])
        }
    )