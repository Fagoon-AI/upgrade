import json
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from src.services.channel_adapter.webhook_gateway import WebhookGatewayService

router = APIRouter()


@router.get("/{channel}/{agent_id}")
async def verify_webhook(
    channel: str,
    agent_id: str,
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if not hub_mode or not hub_verify_token or not hub_challenge:
        raise HTTPException(status_code=400, detail="Missing webhook verification parameters.")

    logger.info("--- Webhook Verification Attempt ---")
    logger.info("channel=%s agent_id=%s hub.mode=%s hub.verify_token=%s hub.challenge=%s",
        channel, agent_id, hub_mode, hub_verify_token, hub_challenge)

    # Quick local test: build expected token and check it directly
    expected_token = f"verify_{agent_id}_{channel}"
    logger.info("Expected token format test: %s", expected_token)
    logger.info("Token match (direct): %s", hub_verify_token == expected_token)

    if not hasattr(request.app.state, "agent_manager"):
        raise HTTPException(status_code=500, detail="Application dependencies are not available.")

    gateway = WebhookGatewayService(
        agent_manager=request.app.state.agent_manager,
        chat_service=request.app.state.agent_chat_service,
    )
    try:
        challenge = await gateway.verify_subscription(
            channel,
            agent_id,
            hub_mode,
            hub_verify_token,
            hub_challenge,
        )
        # Return plain text challenge per Meta requirement and include ngrok bypass header (if useful)
        return PlainTextResponse(content=str(challenge), headers={"ngrok-skip-browser-warning": "1"})
    except HTTPException as e:
        logger.error("Verification failed via gateway: %s", e.detail)
        # Fallback: if gateway fails, try direct token check (for debugging)
        if hub_mode == "subscribe" and hub_verify_token == expected_token:
            logger.info("Direct token check PASSED (gateway failed)")
            return PlainTextResponse(content=str(hub_challenge), headers={"ngrok-skip-browser-warning": "1"})
        raise


@router.post("/{channel}/{agent_id}")
async def receive_webhook(
    channel: str,
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    # --- ADD THIS LOGGING ---
    logger.info(f"Received webhook POST for channel={channel}, agent_id={agent_id}")
    logger.info(f"Headers: {dict(request.headers)}")
    # ------------------------

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Request body is required.")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if not hasattr(request.app.state, "agent_manager") or not hasattr(request.app.state, "agent_chat_service"):
        raise HTTPException(status_code=500, detail="Application dependencies are not available.")

    gateway = WebhookGatewayService(
        agent_manager=request.app.state.agent_manager,
        chat_service=request.app.state.agent_chat_service,
    )
    result = await gateway.handle_webhook(
        channel=channel,
        agent_id=agent_id,
        payload=payload,
        headers={k: v for k, v in request.headers.items()},
        body=body,
        background_tasks=background_tasks,
    )
    return JSONResponse(status_code=200, content=result)
