"""Workflow-as-API: publish workflows as callable REST endpoints."""

import re
import asyncio
from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel
from loguru import logger

from src.core.database import get_db
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.workflow_api import WorkflowAPI
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus
from src.api.v1.routers.workflow.deps import get_current_user
from src.schemas.workflow.response import APIResponse

router = APIRouter()


# ============================================================
# MANAGEMENT ENDPOINTS (require user auth)
# ============================================================

@router.post("/workflows/{workflow_id}/publish-api", response_model=APIResponse)
async def publish_workflow_api(
    workflow_id: str,
    slug: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Publish a workflow as a callable API endpoint.
    Returns the API key (shown only once) and the endpoint URL.
    """
    # Load workflow
    workflow = await db.get(Workflow, UUID(workflow_id))
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if str(workflow.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your workflow")

    # Check if already published as API
    existing = await db.execute(
        select(WorkflowAPI).where(WorkflowAPI.workflow_id == UUID(workflow_id))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Workflow already has an API. Revoke first to regenerate.")

    # Generate slug from name if not provided
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', workflow.name.lower()).strip('-')
        slug = f"{slug}-{workflow_id[:8]}"

    # Ensure slug uniqueness
    slug_exists = await db.execute(select(WorkflowAPI).where(WorkflowAPI.slug == slug))
    if slug_exists.scalar_one_or_none():
        slug = f"{slug}-{int(datetime.now().timestamp()) % 10000}"

    # Generate API key
    raw_key, key_hash, key_prefix = WorkflowAPI.generate_api_key()

    # Create API record
    api_record = WorkflowAPI(
        workflow_id=UUID(workflow_id),
        user_id=current_user.id,
        slug=slug,
        api_key_hash=key_hash,
        api_key_prefix=key_prefix,
        is_active=True,
    )
    db.add(api_record)
    await db.commit()
    await db.refresh(api_record)

    base_url = str(request.base_url).rstrip("/") if request else ""

    return APIResponse(
        success=True,
        message="Workflow API published successfully",
        data={
            "api_id": str(api_record.id),
            "slug": slug,
            "api_key": raw_key,  # Only shown once!
            "endpoint": f"{base_url}/api/v1/workflow-api/{slug}/execute",
            "rate_limit_per_minute": api_record.rate_limit_per_minute,
            "warning": "Save your API key now. It cannot be retrieved later."
        }
    )


@router.get("/workflows/{workflow_id}/api-info", response_model=APIResponse)
async def get_workflow_api_info(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get API info for a workflow (without the full key)."""
    result = await db.execute(
        select(WorkflowAPI).where(
            WorkflowAPI.workflow_id == UUID(workflow_id),
            WorkflowAPI.user_id == current_user.id,
        )
    )
    api_record = result.scalar_one_or_none()
    if not api_record:
        raise HTTPException(status_code=404, detail="No API published for this workflow")

    return APIResponse(
        success=True,
        message="Workflow API info",
        data={
            "api_id": str(api_record.id),
            "slug": api_record.slug,
            "api_key_prefix": api_record.api_key_prefix,
            "is_active": api_record.is_active,
            "rate_limit_per_minute": api_record.rate_limit_per_minute,
            "timeout_seconds": api_record.timeout_seconds,
            "total_calls": api_record.total_calls,
            "last_called_at": api_record.last_called_at.isoformat() if api_record.last_called_at else None,
            "created_at": api_record.created_at.isoformat(),
        }
    )


@router.delete("/workflows/{workflow_id}/api", response_model=APIResponse)
async def revoke_workflow_api(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Revoke API access for a workflow."""
    result = await db.execute(
        select(WorkflowAPI).where(
            WorkflowAPI.workflow_id == UUID(workflow_id),
            WorkflowAPI.user_id == current_user.id,
        )
    )
    api_record = result.scalar_one_or_none()
    if not api_record:
        raise HTTPException(status_code=404, detail="No API found for this workflow")

    await db.delete(api_record)
    await db.commit()

    return APIResponse(success=True, message="Workflow API revoked")


class UpdateWorkflowApiRequest(BaseModel):
    is_active: Optional[bool] = None
    rate_limit: Optional[int] = None
    timeout: Optional[int] = None


@router.patch("/workflows/{workflow_id}/api", response_model=APIResponse)
async def update_workflow_api(
    workflow_id: str,
    body: UpdateWorkflowApiRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update API settings (active status, rate limit, timeout)."""
    result = await db.execute(
        select(WorkflowAPI).where(
            WorkflowAPI.workflow_id == UUID(workflow_id),
            WorkflowAPI.user_id == current_user.id,
        )
    )
    api_record = result.scalar_one_or_none()
    if not api_record:
        raise HTTPException(status_code=404, detail="No API found")

    if body.is_active is not None:
        api_record.is_active = body.is_active
    if body.rate_limit is not None:
        api_record.rate_limit_per_minute = max(1, min(body.rate_limit, 1000))
    if body.timeout is not None:
        api_record.timeout_seconds = max(10, min(body.timeout, 600))

    await db.commit()

    return APIResponse(success=True, message="API settings updated")


# ============================================================
# PUBLIC EXECUTION ENDPOINT (API key auth, no user session)
# ============================================================

@router.post("/workflow-api/{slug}/execute")
async def execute_workflow_via_api(
    slug: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a workflow via its published API.

    Auth: X-API-Key header
    Input: JSON body with 'input' field
    Output: Final workflow result

    Example:
        curl -X POST https://your-domain/api/v1/workflow-api/my-workflow/execute \
          -H "X-API-Key: wfapi_xxxxx" \
          -H "Content-Type: application/json" \
          -d '{"input": "Hello, summarize this for me"}'
    """
    # 1. Find API record by slug
    result = await db.execute(select(WorkflowAPI).where(WorkflowAPI.slug == slug))
    api_record = result.scalar_one_or_none()

    if not api_record:
        raise HTTPException(status_code=404, detail="API endpoint not found")

    if not api_record.is_active:
        raise HTTPException(status_code=403, detail="This API endpoint is disabled")

    # 2. Validate API key
    key_hash = WorkflowAPI.hash_key(x_api_key)
    if key_hash != api_record.api_key_hash:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 3. Parse input
    try:
        body = await request.json()
    except Exception:
        body = {}

    user_input = body.get("input", body.get("prompt", ""))
    extra_vars = body.get("variables", {})
    initial_input = {"input": user_input, **extra_vars}

    # 4. Load workflow
    workflow = await db.get(Workflow, api_record.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.graph_definition or not workflow.graph_definition.get("nodes"):
        raise HTTPException(status_code=400, detail="Workflow has no nodes")

    # 5. Create execution record
    import uuid as uuid_mod
    execution_id = uuid_mod.uuid4()
    execution = WorkflowExecution(
        id=execution_id,
        workflow_id=workflow.id,
        status=ExecutionStatus.PENDING,
        trigger_type="API",
        graph_snapshot=workflow.graph_definition,
        context_data={"input": initial_input},
    )
    db.add(execution)
    await db.commit()

    # 6. Run workflow synchronously (within timeout)
    try:
        from src.tasks.workflow import execute_workflow_logic
        result = await asyncio.wait_for(
            execute_workflow_logic(
                execution_id=str(execution_id),
                workflow_id=str(workflow.id),
                initial_input=initial_input,
            ),
            timeout=api_record.timeout_seconds
        )
    except asyncio.TimeoutError:
        # Mark execution as timed out
        execution = await db.get(WorkflowExecution, execution_id)
        if execution:
            execution.status = ExecutionStatus.TIMEOUT
            execution.finished_at = datetime.now(timezone.utc)
            await db.commit()
        raise HTTPException(status_code=504, detail="Workflow execution timed out")
    except Exception as e:
        logger.error(f"API execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")

    # 7. Fetch final results
    await db.refresh(execution)
    execution = await db.get(WorkflowExecution, execution_id)

    # 8. Update API usage stats
    api_record.total_calls += 1
    api_record.last_called_at = datetime.now(timezone.utc)
    await db.commit()

    # 9. Extract final output (last node's output)
    final_output = None
    if execution and execution.results:
        # results contains node outputs keyed by node_id
        outputs = execution.results
        if isinstance(outputs, dict):
            # Get the last non-start node output
            for node in reversed(workflow.graph_definition.get("nodes", [])):
                node_id = node.get("id", "")
                if node_id in outputs and "start" not in node_id.lower():
                    final_output = outputs[node_id]
                    break
            # Fallback: just return all outputs
            if final_output is None:
                final_output = outputs

    return {
        "success": True,
        "execution_id": str(execution_id),
        "status": execution.status.value if execution else "UNKNOWN",
        "output": final_output,
        "usage": {
            "duration_ms": (
                int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                if execution and execution.finished_at and execution.started_at
                else None
            )
        }
    }
