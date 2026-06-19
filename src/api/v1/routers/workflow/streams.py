"""
WebSocket Streaming with Event-Driven Architecture.

Engineering Committee Design Decisions:
- Principal System Design Engineer: Event-driven instead of polling
- Principal Backend Engineer: Proper connection lifecycle management
- Principal System Architect: Graceful handling of disconnections
- Principal Security Engineer: JWT authentication for WebSocket connections

Critical Fixes:
- SYS-002: Replaced CPU-bound polling with proper async pub/sub
- SEC-005: Added WebSocket authentication

Version: 2.1.0
"""

import asyncio
import json
from typing import Optional, Dict, Any, Set
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request, status, HTTPException
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from loguru import logger

from src.core.config import settings
from src.core.security import ALGORITHM


router = APIRouter()


# ============================================================
# WEBSOCKET AUTHENTICATION
# ============================================================

async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = None
) -> Optional[UUID]:
    """
    Authenticate WebSocket connection using JWT token.

    Token can be provided via:
    1. Query parameter: ?token=<jwt>
    2. Cookie: access_token

    Args:
        websocket: The WebSocket connection
        token: Optional token from query parameter

    Returns:
        User UUID if authenticated, None if auth fails

    Note:
        Unlike HTTP endpoints, WebSocket cannot use Authorization header
        directly. Token must be sent via query param or cookie.
    """
    # Try query parameter first
    auth_token = token

    # Fall back to cookie
    if not auth_token:
        cookie = websocket.cookies.get("access_token")
        if cookie:
            # Cookie might have "Bearer " prefix
            if cookie.startswith("Bearer "):
                auth_token = cookie[7:]
            else:
                auth_token = cookie

    if not auth_token:
        logger.debug("WebSocket connection: No token provided")
        return None

    try:
        # Validate JWT
        payload = jwt.decode(
            auth_token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM]
        )

        # Check token type
        token_type = payload.get("type", "access")
        if token_type != "access":
            logger.warning("WebSocket: Invalid token type")
            return None

        # Extract user ID
        user_id_str = payload.get("sub")
        if not user_id_str:
            logger.warning("WebSocket: Token missing subject")
            return None

        return UUID(user_id_str)

    except JWTError as e:
        logger.debug(f"WebSocket JWT validation failed: {e}")
        return None
    except ValueError as e:
        logger.debug(f"WebSocket: Invalid user ID format: {e}")
        return None


async def require_websocket_auth(
    websocket: WebSocket,
    token: Optional[str] = None
) -> UUID:
    """
    Require authentication for WebSocket connection.

    Closes connection with 4001 code if not authenticated.

    Args:
        websocket: The WebSocket connection
        token: Optional token from query parameter

    Returns:
        User UUID if authenticated

    Raises:
        Closes WebSocket if not authenticated
    """
    user_id = await authenticate_websocket(websocket, token)

    if not user_id:
        await websocket.close(code=4001, reason="Authentication required")
        raise WebSocketDisconnect(code=4001, reason="Authentication required")

    return user_id


class ConnectionManager:
    """
    Manages WebSocket connections for execution streaming.

    Features:
    - Tracks active connections per execution
    - Broadcasts messages to all subscribers
    - Handles disconnections gracefully
    - Provides connection statistics
    """

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, execution_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        await websocket.accept()

        async with self._lock:
            if execution_id not in self._connections:
                self._connections[execution_id] = set()
            self._connections[execution_id].add(websocket)

        logger.info(f"WebSocket connected: {execution_id}")

    async def disconnect(self, execution_id: str, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            if execution_id in self._connections:
                self._connections[execution_id].discard(websocket)
                if not self._connections[execution_id]:
                    del self._connections[execution_id]

        logger.info(f"WebSocket disconnected: {execution_id}")

    async def broadcast(self, execution_id: str, message: str) -> int:
        """
        Broadcasts a message to all connections for an execution.

        Returns:
            Number of connections that received the message
        """
        async with self._lock:
            connections = self._connections.get(execution_id, set()).copy()

        if not connections:
            return 0

        sent_count = 0
        dead_connections = []

        for websocket in connections:
            try:
                await websocket.send_text(message)
                sent_count += 1
            except Exception:
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    if execution_id in self._connections:
                        self._connections[execution_id].discard(ws)

        return sent_count

    def get_connection_count(self, execution_id: str) -> int:
        """Returns number of active connections for an execution."""
        return len(self._connections.get(execution_id, set()))

    def get_stats(self) -> Dict[str, Any]:
        """Returns connection statistics."""
        return {
            "total_executions": len(self._connections),
            "total_connections": sum(len(c) for c in self._connections.values()),
            "connections_per_execution": {
                eid: len(conns) for eid, conns in self._connections.items()
            }
        }


# Global connection manager
connection_manager = ConnectionManager()


async def redis_listener(execution_id: str, pubsub: Any) -> None:
    """
    Background task that listens to PubSub and broadcasts to WebSockets.

    This replaces the old polling pattern with proper pub/sub.
    """
    channel = f"exec_trace:{execution_id}"

    try:
        async for message in pubsub.subscribe(channel, timeout=30.0):
            # Broadcast to all connected WebSocket clients
            await connection_manager.broadcast(execution_id, message)

    except asyncio.CancelledError:
        logger.debug(f"PubSub listener cancelled: {execution_id}")
    except Exception as e:
        logger.error(f"PubSub listener error: {execution_id} - {e}")


@router.websocket("/{execution_id}")
async def execution_stream(
        websocket: WebSocket,
        execution_id: str,
        token: Optional[str] = Query(
            default=None,
            description="JWT access token for authentication"
        )
):
    """
    Real-time trace stream for workflow executions.

    Authentication:
    - Token can be provided via query parameter: ?token=<jwt>
    - Or via access_token cookie (for browser clients)
    - Connection closed with code 4001 if not authenticated

    Event-Driven Architecture:
    1. Authenticate WebSocket connection
    2. Start Redis subscription in background
    3. Forward Redis messages to WebSocket
    4. Clean up on disconnect

    Protocol:
    - Server sends JSON trace events
    - Client can send "ping" for keepalive
    - Server responds with "pong"

    WebSocket Close Codes:
    - 4001: Authentication required
    - 1000: Normal closure
    - 1011: Server error
    """
    # Authenticate before accepting connection
    try:
        user_id = await require_websocket_auth(websocket, token)
        logger.info(f"WebSocket authenticated: user={user_id}, execution={execution_id}")
    except WebSocketDisconnect:
        return

    await connection_manager.connect(execution_id, websocket)

    # Start Redis listener as background task
    listener_task = asyncio.create_task(redis_listener(execution_id, websocket.app.state.pubsub))

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "execution_id": execution_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Main loop: handle incoming messages (keepalive, etc.)
        while True:
            try:
                # Wait for client messages with timeout
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # 1 minute timeout
                )

                # Handle ping/pong for keepalive
                if data == "ping":
                    await websocket.send_text("pong")
                elif data == "close":
                    break

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({
                        "type": "keepalive",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected: {execution_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {execution_id} - {e}")
    finally:
        # Cancel Redis listener
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

        # Unregister connection
        await connection_manager.disconnect(execution_id, websocket)


@router.websocket("/multi")
async def multi_execution_stream(
        websocket: WebSocket,
        execution_ids: str = Query(..., description="Comma-separated execution IDs"),
        token: Optional[str] = Query(
            default=None,
            description="JWT access token for authentication"
        )
):
    """
    Stream multiple executions over a single WebSocket.

    Useful for dashboards monitoring multiple workflows.

    Authentication:
    - Token can be provided via query parameter: ?token=<jwt>
    - Or via access_token cookie (for browser clients)
    - Connection closed with code 4001 if not authenticated
    """
    # Authenticate before accepting connection
    try:
        user_id = await require_websocket_auth(websocket, token)
        logger.info(f"Multi-stream WebSocket authenticated: user={user_id}")
    except WebSocketDisconnect:
        return

    ids = [eid.strip() for eid in execution_ids.split(",") if eid.strip()]

    if not ids:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Start listeners for all executions
    listener_tasks = []

    async def forward_messages(eid: str):
        """Forward messages from one execution to the WebSocket."""
        channel = f"exec_trace:{eid}"
        try:
            pubsub = websocket.app.state.pubsub
            async for message in pubsub.subscribe(channel, timeout=30.0):
                # Add execution ID to message for client routing
                try:
                    data = json.loads(message)
                    data["execution_id"] = eid
                    await websocket.send_json(data)
                except json.JSONDecodeError:
                    await websocket.send_text(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Multi-stream error for {eid}: {e}")

    for eid in ids:
        task = asyncio.create_task(forward_messages(eid))
        listener_tasks.append(task)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "execution_ids": ids,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0
                )

                if data == "ping":
                    await websocket.send_text("pong")
                elif data == "close":
                    break

            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "keepalive",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Multi-stream WebSocket error: {e}")
    finally:
        # Cancel all listeners
        for task in listener_tasks:
            task.cancel()
        await asyncio.gather(*listener_tasks, return_exceptions=True)


@router.get("")
async def sse_execution_stream(
        request: Request,
        channel: str = Query(..., description="PubSub channel to subscribe to"),
        token: Optional[str] = Query(None),
        access_token: Optional[str] = Query(None)
):
    """
    Server-Sent Events (SSE) endpoint for real-time execution traces.
    
    This endpoint supports EventSource connections from the frontend.
    Authentication is handled by AuthMiddleware intercepting the token query parameters.
    """
    current_user = getattr(request.state, "user", None)
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Authentication required for SSE stream"
        )
        
    async def event_generator():
        try:
            pubsub = request.app.state.pubsub
            async for message in pubsub.subscribe(channel, timeout=30.0):
                # Ensure the message is formatted properly for SSE (data: <payload>\n\n)
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            logger.debug(f"SSE listener cancelled for channel: {channel}")
        except Exception as e:
            logger.error(f"SSE listener error on {channel}: {e}")
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/stats")
async def get_stream_stats(request: Request):
    """
    Returns WebSocket streaming statistics.

    Useful for monitoring and debugging.
    """
    return {
        "websocket": connection_manager.get_stats(),
        "redis": await request.app.state.pubsub.health_check()
    }


# ============================================================
# HELPER FUNCTIONS FOR EXECUTORS
# ============================================================

async def emit_trace(execution_id: str, data: Dict[str, Any]) -> bool:
    """
    Emits a trace event to all subscribers.

    Called by the executor to stream progress updates.

    Args:
        execution_id: The execution being traced
        data: Trace data to emit

    Returns:
        True if published successfully
    """
    channel = f"exec_trace:{execution_id}"
    message = json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data
    })

    try:
        from src.core.runtime import get_runtime
        runtime = get_runtime()
        logger.info(f"EMIT_TRACE: channel={channel}, runtime={runtime}, has_pubsub={hasattr(runtime, 'pubsub') if runtime else False}")
        if runtime and runtime.pubsub:
            count = await runtime.pubsub.publish(channel, message)
            logger.info(f"EMIT_TRACE: published OK to {channel}, delivered_to={count} subscribers")
            return True
        logger.warning(f"EMIT_TRACE: SKIPPED - runtime={runtime}, pubsub={getattr(runtime, 'pubsub', 'MISSING')}")
        return False
    except Exception as e:
        logger.error(f"EMIT_TRACE FAILED: {e}", exc_info=True)
        return False


async def emit_node_start(
        execution_id: str,
        node_id: str,
        node_type: str,
        attempt: int = 1
) -> None:
    """Helper to emit node start event."""
    await emit_trace(execution_id, {
        "node_id": node_id,
        "node_type": node_type,
        "status": "RUNNING",
        "attempt": attempt
    })


async def emit_node_success(
        execution_id: str,
        node_id: str,
        duration_ms: int
) -> None:
    """Helper to emit node success event."""
    await emit_trace(execution_id, {
        "node_id": node_id,
        "status": "SUCCESS",
        "duration_ms": duration_ms
    })


async def emit_node_failure(
        execution_id: str,
        node_id: str,
        error: str,
        attempt: int = 1
) -> None:
    """Helper to emit node failure event."""
    await emit_trace(execution_id, {
        "node_id": node_id,
        "status": "FAILED",
        "error": error,
        "attempt": attempt
    })


async def emit_execution_complete(
        execution_id: str,
        status: str,
        total_duration_ms: int
) -> None:
    """Helper to emit execution completion event."""
    await emit_trace(execution_id, {
        "type": "execution_complete",
        "status": status,
        "total_duration_ms": total_duration_ms
    })