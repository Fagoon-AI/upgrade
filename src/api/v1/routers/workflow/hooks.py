import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from loguru import logger

from src.core.database import get_db
from src.models.sql.workflow.webhook import Webhook
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus
from src.models.sql.workflow.execution import WorkflowExecution, ExecutionStatus
from src.schemas.workflow.response import APIResponse
from src.services.workflow.webhook_verifier import WebhookVerifier


router = APIRouter()


# ============================================================
# CONFIGURATION
# ============================================================

# Maximum payload size (5MB)
MAX_PAYLOAD_SIZE = 5 * 1024 * 1024

# Providers and their signature headers
PROVIDER_SIGNATURE_HEADERS = {
    "github": ["x-hub-signature-256", "x-hub-signature"],
    "stripe": ["stripe-signature"],
    "slack": ["x-slack-signature"],
    "shopify": ["x-shopify-hmac-sha256"],
    "twilio": ["x-twilio-signature"],
    "generic": ["x-signature", "x-webhook-signature", "signature"],
}

# Provider event ID headers (for idempotency)
PROVIDER_EVENT_ID_HEADERS = {
    "github": "x-github-delivery",
    "stripe": "stripe-request-id",
    "slack": "x-slack-request-timestamp",
    "shopify": "x-shopify-webhook-id",
    "generic": "x-request-id",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def detect_provider(headers: Dict[str, str], webhook_name: str) -> str:
    """
    Detects webhook provider from headers or webhook name.

    Returns provider name for signature verification.
    """
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # Check for provider-specific headers
    for provider, sig_headers in PROVIDER_SIGNATURE_HEADERS.items():
        for header in sig_headers:
            if header in headers_lower:
                return provider

    # Check webhook name for provider hints
    webhook_name_lower = webhook_name.lower()
    for provider in PROVIDER_SIGNATURE_HEADERS.keys():
        if provider in webhook_name_lower:
            return provider

    return "generic"


def get_signature_from_headers(headers: Dict[str, str], provider: str) -> Optional[str]:
    """Extracts signature from headers based on provider."""
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # Get provider-specific headers
    sig_headers = PROVIDER_SIGNATURE_HEADERS.get(provider, [])

    # Also check generic headers
    all_headers = sig_headers + PROVIDER_SIGNATURE_HEADERS["generic"]

    for header in all_headers:
        if header in headers_lower:
            return headers_lower[header]

    return None


def get_event_id(headers: Dict[str, str], provider: str) -> Optional[str]:
    """Extracts event ID for idempotency."""
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # Provider-specific header
    provider_header = PROVIDER_EVENT_ID_HEADERS.get(provider)
    if provider_header and provider_header in headers_lower:
        return headers_lower[provider_header]

    # Generic fallbacks
    for header in ["x-request-id", "x-correlation-id", "request-id"]:
        if header in headers_lower:
            return headers_lower[header]

    return None


def generate_idempotency_key(
        slug: str,
        event_id: Optional[str],
        payload_hash: str
) -> str:
    """
    Generates idempotency key for deduplication.

    Uses event ID if available, otherwise uses payload hash.
    """
    if event_id:
        return f"{slug}:{event_id}"
    return f"{slug}:hash:{payload_hash[:32]}"


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Sanitizes headers for storage.

    Removes sensitive headers and limits size.
    """
    sensitive_headers = {
        "authorization", "cookie", "x-api-key", "api-key",
        "x-auth-token", "x-access-token"
    }

    sanitized = {}
    for key, value in headers.items():
        key_lower = key.lower()

        # Skip sensitive headers
        if key_lower in sensitive_headers:
            sanitized[key] = "[REDACTED]"
            continue

        # Limit value size
        if len(value) > 500:
            sanitized[key] = value[:500] + "...[truncated]"
        else:
            sanitized[key] = value

    return sanitized


# ============================================================
# WEBHOOK ENDPOINTS
# ============================================================

@router.post("/{slug}", response_model=APIResponse)
async def ingest_webhook_trigger(
        slug: str,
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    """
    Webhook Ingestor.

    Features:
    - Multi-provider signature verification
    - Idempotency (duplicate detection)
    - Payload size limits
    - Workflow validation
    - Async execution dispatch

    Flow:
    1. Lookup webhook by slug
    2. Validate payload size
    3. Verify signature (if configured)
    4. Check for duplicate (idempotency)
    5. Validate workflow is runnable
    6. Create execution record
    7. Dispatch to task queue
    """
    request_start = datetime.now(timezone.utc)

    # 1. Lookup Webhook
    query = select(Webhook).where(
        Webhook.slug == slug,
        Webhook.is_active == True
    )
    result = await db.execute(query)
    hook = result.scalar_one_or_none()

    if not hook:
        logger.warning(f"Webhook not found or inactive: {slug}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found or inactive"
        )

    # 2. Capture and Validate Payload
    try:
        raw_body = await request.body()
    except Exception as e:
        logger.error(f"Failed to read request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read request body"
        )

    # Check payload size
    if len(raw_body) > MAX_PAYLOAD_SIZE:
        logger.warning(f"Payload too large for webhook {slug}: {len(raw_body)} bytes")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload exceeds maximum size of {MAX_PAYLOAD_SIZE} bytes"
        )

    # Get headers
    headers = dict(request.headers)
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # 3. Detect Provider and Verify Signature
    provider = detect_provider(headers, hook.name)

    if hook.secret_key:
        signature = get_signature_from_headers(headers, provider)

        if not signature:
            logger.warning(f"Missing signature for webhook {slug}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature"
            )

        # Use enhanced verifier
        verification_result = WebhookVerifier.verify(
            payload=raw_body,
            signature=signature,
            secret=hook.secret_key,
            provider_type=provider,
            headers=headers
        )

        if not verification_result.is_valid:
            logger.warning(
                f"Invalid signature for webhook {slug}: {verification_result.error}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid webhook signature: {verification_result.error}"
            )

        logger.debug(f"Signature verified for {slug} (provider: {provider})")

    # 4. Generate Idempotency Key
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    event_id = get_event_id(headers, provider)
    idempotency_key = generate_idempotency_key(slug, event_id, payload_hash)

    # 5. Parse Payload
    try:
        if raw_body:
            content_type = headers_lower.get("content-type", "")

            if "application/json" in content_type:
                body = json.loads(raw_body)
            elif "application/x-www-form-urlencoded" in content_type:
                # Parse form data
                body = dict(request.query_params)
                body["_raw"] = raw_body.decode("utf-8", errors="replace")
            else:
                # Try JSON, fallback to raw
                try:
                    body = json.loads(raw_body)
                except json.JSONDecodeError:
                    body = {"_raw": raw_body.decode("utf-8", errors="replace")}
        else:
            body = {}
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON payload for webhook {slug}: {e}")
        body = {"_raw": raw_body.decode("utf-8", errors="replace"), "_parse_error": str(e)}
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        body = {"_error": str(e)}

    # 6. Validate Workflow is Runnable
    workflow_query = select(Workflow).where(Workflow.id == hook.workflow_id)
    workflow_result = await db.execute(workflow_query)
    workflow = workflow_result.scalar_one_or_none()

    if not workflow:
        logger.error(f"Workflow not found for webhook {slug}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated workflow not found"
        )

    if workflow.status == WorkflowStatus.ARCHIVED:
        logger.warning(f"Workflow archived for webhook {slug}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Associated workflow is archived"
        )

    # 7. Build Execution Input
    initial_input = {
        "trigger": "webhook",
        "webhook_metadata": {
            "slug": slug,
            "provider": provider,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
            "received_at": request_start.isoformat(),
            "headers": sanitize_headers(headers),
            "content_type": headers_lower.get("content-type"),
            "payload_size": len(raw_body)
        },
        "payload": body
    }

    # 8. Create Execution Record with Idempotency Check
    new_execution = WorkflowExecution(
        workflow_id=hook.workflow_id,
        status=ExecutionStatus.PENDING,
        trigger_type="WEBHOOK",
        external_event_id=idempotency_key,
        graph_snapshot=workflow.graph_definition,
        context_data={}
    )

    try:
        db.add(new_execution)
        await db.commit()
        await db.refresh(new_execution)
    except IntegrityError:
        # Duplicate event - idempotency working
        await db.rollback()
        logger.info(f"Duplicate webhook event for {slug}: {idempotency_key}")
        return APIResponse(
            success=True,
            message="Event already processed (duplicate)",
            data={
                "status": "DUPLICATE",
                "idempotency_key": idempotency_key
            }
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create execution for webhook {slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create execution record"
        )

    # 9. Dispatch to Task Queue via dual-mode queue abstraction
    try:
        request.app.state.queue.enqueue(
            "execute_workflow_task",
            execution_id=str(new_execution.id),
            workflow_id=str(hook.workflow_id),
            initial_input=initial_input
        )
    except Exception as e:
        # Log but don't fail - execution record exists
        logger.error(f"Failed to dispatch task for webhook {slug}: {e}")
        # Update execution status to indicate dispatch failure
        new_execution.status = ExecutionStatus.FAILED
        new_execution.context_data = {"error": f"Task dispatch failed: {e}"}
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue workflow execution"
        )

    # 10. Success Response
    processing_time = (datetime.now(timezone.utc) - request_start).total_seconds()

    logger.info(
        f"Webhook processed: {slug} -> execution {new_execution.id} "
        f"(provider: {provider}, time: {processing_time:.3f}s)"
    )

    return APIResponse(
        success=True,
        message="Webhook received and workflow queued",
        data={
            "execution_id": str(new_execution.id),
            "workflow_id": str(hook.workflow_id),
            "idempotency_key": idempotency_key,
            "provider": provider,
            "processing_time_ms": int(processing_time * 1000)
        }
    )


@router.get("/{slug}", response_model=APIResponse)
async def get_webhook_info(
        slug: str,
        db: AsyncSession = Depends(get_db)
):
    """
    Webhook health check and metadata endpoint.

    Useful for:
    - Verifying webhook is active
    - Getting webhook configuration
    - Health checks from providers
    """
    query = select(Webhook).where(Webhook.slug == slug)
    result = await db.execute(query)
    hook = result.scalar_one_or_none()

    if not hook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )

    return APIResponse(
        success=True,
        message="Webhook found",
        data={
            "slug": slug,
            "name": hook.name,
            "active": hook.is_active,
            "has_secret": bool(hook.secret_key),
            "created_at": hook.created_at.isoformat() if hook.created_at else None
        }
    )


@router.head("/{slug}")
async def webhook_health_check(
        slug: str,
        db: AsyncSession = Depends(get_db)
):
    """
    HEAD endpoint for webhook health checks.

    Some providers (like Slack) use HEAD requests to verify endpoints.
    """
    query = select(Webhook).where(Webhook.slug == slug, Webhook.is_active == True)
    result = await db.execute(query)
    hook = result.scalar_one_or_none()

    if not hook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return None  # 200 OK with no body


@router.options("/{slug}")
async def webhook_options(slug: str):
    """
    OPTIONS endpoint for CORS preflight.

    Required for browser-based webhook testing.
    """
    return {
        "methods": ["GET", "POST", "HEAD", "OPTIONS"],
        "headers": ["Content-Type", "X-Signature", "X-Hub-Signature-256"]
    }