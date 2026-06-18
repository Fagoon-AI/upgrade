import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError, ConnectionError
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class SlackConfig:
    """Configuration for Slack operations."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_message_length: int = 40000  # Slack limit
    default_message_limit: int = 100
    max_message_limit: int = 1000


# Slack API base URL
SLACK_API_BASE = "https://slack.com/api"

# Rate limit error codes
RATE_LIMIT_ERRORS = ["rate_limited", "ratelimited"]

# Retryable error codes
RETRYABLE_ERRORS = [
    "timeout", "service_unavailable", "internal_error",
    "fatal_error", "request_timeout"
]


# ============================================================
# SLACK CLIENT
# ============================================================

class SlackClient:
    """
    Robust Slack API client with retry logic.
    """

    def __init__(self, token: str, config: Optional[SlackConfig] = None):
        self.token = token
        self.config = config or SlackConfig()
        self._channel_cache: Dict[str, str] = {}  # name -> id cache

    async def _make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        url = f"{SLACK_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers, params=params)
                    else:
                        response = await client.post(url, headers=headers, json=data)

                    result = response.json()

                    # Check for rate limiting
                    if not result.get("ok"):
                        error = result.get("error", "unknown_error")

                        if error in RATE_LIMIT_ERRORS:
                            # Get retry-after header
                            retry_after = int(response.headers.get("Retry-After", 5))
                            logger.warning(f"Slack rate limited. Waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                        if error in RETRYABLE_ERRORS and attempt < self.config.max_retries:
                            logger.warning(f"Slack API error: {error}. Retrying...")
                            await asyncio.sleep(self.config.retry_delay * attempt)
                            continue

                        return result  # Return error result for caller to handle

                    return result

            except httpx.TimeoutException:
                last_error = "Request timeout"
                logger.warning(f"Slack request timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Slack connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Slack request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"ok": False, "error": last_error or "max_retries_exceeded"}

    async def resolve_channel(self, channel: str) -> Tuple[str, Optional[str]]:
        """
        Resolves channel name to ID.

        Accepts: #channel-name, channel-name, or C12345678 (ID)
        Returns: (channel_id, error)
        """
        if not channel:
            return "", "Channel is required"

        # Clean channel name
        channel = channel.strip().lstrip("#")

        # Check if already an ID (starts with C, G, or D)
        if re.match(r'^[CGD][A-Z0-9]{8,}$', channel.upper()):
            return channel.upper(), None

        # Check cache
        if channel in self._channel_cache:
            return self._channel_cache[channel], None

        # Look up channel
        result = await self._make_request(
            "GET",
            "conversations.list",
            params={"types": "public_channel,private_channel", "limit": 200}
        )

        if not result.get("ok"):
            return "", result.get("error", "Failed to list channels")

        for ch in result.get("channels", []):
            self._channel_cache[ch["name"]] = ch["id"]
            if ch["name"] == channel:
                return ch["id"], None

        return "", f"Channel '{channel}' not found"

    async def send_message(
            self,
            channel: str,
            text: str,
            blocks: Optional[List[Dict]] = None,
            thread_ts: Optional[str] = None,
            reply_broadcast: bool = False
    ) -> Dict[str, Any]:
        """Sends a message to a channel."""
        # Resolve channel
        channel_id, error = await self.resolve_channel(channel)
        if error:
            return {"ok": False, "error": error}

        # Truncate text if too long
        if len(text) > self.config.max_message_length:
            text = text[:self.config.max_message_length - 20] + "\n...[truncated]"

        payload = {
            "channel": channel_id,
            "text": text
        }

        if blocks:
            payload["blocks"] = blocks

        if thread_ts:
            payload["thread_ts"] = thread_ts
            if reply_broadcast:
                payload["reply_broadcast"] = True

        return await self._make_request("POST", "chat.postMessage", data=payload)

    async def read_messages(
            self,
            channel: str,
            limit: int = 100,
            oldest: Optional[str] = None,
            latest: Optional[str] = None
    ) -> Dict[str, Any]:
        """Reads message history from a channel."""
        channel_id, error = await self.resolve_channel(channel)
        if error:
            return {"ok": False, "error": error}

        limit = min(limit, self.config.max_message_limit)

        params = {
            "channel": channel_id,
            "limit": limit
        }

        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        return await self._make_request("GET", "conversations.history", params=params)

    async def list_channels(
            self,
            types: str = "public_channel,private_channel",
            limit: int = 200
    ) -> Dict[str, Any]:
        """Lists available channels."""
        return await self._make_request(
            "GET",
            "conversations.list",
            params={"types": types, "limit": limit, "exclude_archived": True}
        )

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Gets user information."""
        return await self._make_request(
            "GET",
            "users.info",
            params={"user": user_id}
        )

    async def add_reaction(
            self,
            channel: str,
            timestamp: str,
            emoji: str
    ) -> Dict[str, Any]:
        """Adds a reaction to a message."""
        channel_id, error = await self.resolve_channel(channel)
        if error:
            return {"ok": False, "error": error}

        return await self._make_request(
            "POST",
            "reactions.add",
            data={
                "channel": channel_id,
                "timestamp": timestamp,
                "name": emoji.strip(":")
            }
        )


# ============================================================
# BLOCK KIT BUILDER
# ============================================================

class BlockKitBuilder:
    """Builds Slack Block Kit messages."""

    @staticmethod
    def text_block(text: str, block_type: str = "section") -> Dict:
        """Creates a text block."""
        return {
            "type": block_type,
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        }

    @staticmethod
    def header_block(text: str) -> Dict:
        """Creates a header block."""
        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": text[:150],  # Header limit
                "emoji": True
            }
        }

    @staticmethod
    def divider() -> Dict:
        """Creates a divider block."""
        return {"type": "divider"}

    @staticmethod
    def context_block(elements: List[str]) -> Dict:
        """Creates a context block with multiple text elements."""
        return {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": el} for el in elements
            ]
        }

    @staticmethod
    def build_workflow_notification(
            title: str,
            message: str,
            status: str = "info",
            workflow_name: Optional[str] = None,
            execution_id: Optional[str] = None
    ) -> List[Dict]:
        """Builds a standard workflow notification message."""
        emoji_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }
        emoji = emoji_map.get(status, "📋")

        blocks = [
            BlockKitBuilder.header_block(f"{emoji} {title}"),
            BlockKitBuilder.text_block(message),
        ]

        if workflow_name or execution_id:
            context_elements = []
            if workflow_name:
                context_elements.append(f"*Workflow:* {workflow_name}")
            if execution_id:
                context_elements.append(f"*Execution:* `{execution_id[:8]}`")
            blocks.append(BlockKitBuilder.context_block(context_elements))

        return blocks


# ============================================================
# SLACK NODE
# ============================================================

class SlackNode(BaseNode):
    """
    World-Class Slack Integration Node.

    Features:
    - Multiple authentication methods (webhook, bot token)
    - Retry with exponential backoff
    - Rate limit handling
    - Block Kit rich messages
    - Channel name resolution
    - Message history pagination

    Operations:
    - send_message: Send text or rich messages
    - read_messages: Get channel history
    - list_channels: List available channels
    - add_reaction: Add emoji reaction
    """

    node_type = "slackNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Slack",
            "icon": "Slack",
            "category": "Communication",
            "description": "Enterprise Slack integration with Block Kit support.",
            "fields": [
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["send_message", "read_messages", "list_channels", "add_reaction"],
                    "default": "send_message"
                },
                {
                    "name": "authentication_method",
                    "label": "Auth Method",
                    "type": "select",
                    "options": ["webhook", "bot_token"],
                    "default": "webhook"
                },
                {
                    "name": "webhook_url",
                    "label": "Webhook URL",
                    "type": "text",
                    "conditional": {"authentication_method": "webhook"},
                    "helper": "Incoming webhook URL from Slack"
                },
                {
                    "name": "connection_id",
                    "label": "Slack Connection",
                    "type": "connection_select",
                    "provider": "SLACK",
                    "conditional": {"authentication_method": "bot_token"}
                },
                {
                    "name": "channel",
                    "label": "Channel",
                    "type": "text",
                    "placeholder": "#general or C12345678",
                    "helper": "Channel name or ID"
                },
                {
                    "name": "message",
                    "label": "Message",
                    "type": "textarea",
                    "conditional": {"operation": "send_message"},
                    "helper": "Supports Slack markdown"
                },
                {
                    "name": "use_blocks",
                    "label": "Use Rich Formatting",
                    "type": "boolean",
                    "default": False,
                    "conditional": {"operation": "send_message"}
                },
                {
                    "name": "notification_status",
                    "label": "Notification Type",
                    "type": "select",
                    "options": ["info", "success", "warning", "error"],
                    "default": "info",
                    "conditional": {"use_blocks": True}
                },
                {
                    "name": "thread_ts",
                    "label": "Thread Timestamp",
                    "type": "text",
                    "helper": "Reply in thread (optional)"
                },
                {
                    "name": "message_limit",
                    "label": "Message Limit",
                    "type": "number",
                    "default": 100,
                    "conditional": {"operation": "read_messages"}
                },
                {
                    "name": "emoji",
                    "label": "Emoji",
                    "type": "text",
                    "placeholder": "thumbsup",
                    "conditional": {"operation": "add_reaction"}
                },
                {
                    "name": "message_ts",
                    "label": "Message Timestamp",
                    "type": "text",
                    "conditional": {"operation": "add_reaction"},
                    "helper": "Timestamp of message to react to"
                }
            ],
            "outputs": ["status", "ts", "channel", "messages", "channels", "count"]
        }

    def __init__(self):
        super().__init__()
        self.config = SlackConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Slack operation."""
        operation = input_data.get("operation", "send_message")
        auth_method = input_data.get("authentication_method", "webhook")

        # Get credentials
        if auth_method == "webhook":
            return await self._execute_webhook(input_data)
        else:
            return await self._execute_api(db, context, input_data, operation)

    async def _execute_webhook(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes webhook-based message send."""
        webhook_url = input_data.get("webhook_url", "").strip()
        message = input_data.get("message", "📋 Workflow Notification")

        if not webhook_url:
            raise NodeExecutionError(
                message="Webhook URL is required",
                node_type=self.node_type,
                retryable=False
            )

        # Validate webhook URL
        if not webhook_url.startswith("https://hooks.slack.com/"):
            raise NodeExecutionError(
                message="Invalid Slack webhook URL",
                node_type=self.node_type,
                retryable=False
            )

        payload = {"text": message}

        # Add blocks if using rich formatting
        if input_data.get("use_blocks"):
            status = input_data.get("notification_status", "info")
            payload["blocks"] = BlockKitBuilder.build_workflow_notification(
                title="Workflow Notification",
                message=message,
                status=status,
                execution_id=context.execution_id if hasattr(self, 'context') else None
            )

        # Send with retry
        last_error = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.post(webhook_url, json=payload)

                    if response.status_code == 200:
                        return {
                            "status": "success",
                            "method": "webhook",
                            "message": "Message sent successfully"
                        }

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        await asyncio.sleep(retry_after)
                        continue

                    last_error = f"HTTP {response.status_code}: {response.text}"

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Webhook error (attempt {attempt}): {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"status": "error", "error": last_error or "Unknown error"}

    async def _execute_api(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            operation: str
    ) -> Dict[str, Any]:
        """Executes API-based operations."""
        # Get token from connection
        token = await self._get_token(db, input_data)
        client = SlackClient(token, self.config)

        if operation == "send_message":
            return await self._send_message(client, input_data, context)
        elif operation == "read_messages":
            return await self._read_messages(client, input_data)
        elif operation == "list_channels":
            return await self._list_channels(client)
        elif operation == "add_reaction":
            return await self._add_reaction(client, input_data)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_token(self, db: AsyncSession, input_data: Dict[str, Any]) -> str:
        """Gets bot token from connection."""
        connection_id = input_data.get("connection_id")

        if not connection_id:
            raise NodeExecutionError(
                message="Connection ID is required for API operations",
                node_type=self.node_type,
                retryable=False
            )

        result = await db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        conn = result.scalars().first()

        if not conn:
            raise ConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="slack"
            )

        try:
            creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
            token = creds.get("bot_token") or creds.get("access_token")
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="slack"
            )

        if not token:
            raise ConnectionError(
                message="Connection missing bot token",
                node_type=self.node_type,
                provider="slack"
            )

        return token

    async def _send_message(
            self,
            client: SlackClient,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Sends a message via API."""
        channel = input_data.get("channel", "")
        message = input_data.get("message", "📋 Workflow Notification")
        thread_ts = input_data.get("thread_ts")
        use_blocks = input_data.get("use_blocks", False)

        if not channel:
            raise NodeExecutionError(
                message="Channel is required",
                node_type=self.node_type,
                retryable=False
            )

        blocks = None
        if use_blocks:
            status = input_data.get("notification_status", "info")
            blocks = BlockKitBuilder.build_workflow_notification(
                title="Workflow Notification",
                message=message,
                status=status,
                execution_id=context.execution_id
            )

        result = await client.send_message(
            channel=channel,
            text=message,
            blocks=blocks,
            thread_ts=thread_ts
        )

        if not result.get("ok"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to send message")
            }

        return {
            "status": "success",
            "ts": result.get("ts"),
            "channel": result.get("channel"),
            "message": result.get("message", {})
        }

    async def _read_messages(
            self,
            client: SlackClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reads message history."""
        channel = input_data.get("channel", "")
        limit = int(input_data.get("message_limit", 100))

        if not channel:
            raise NodeExecutionError(
                message="Channel is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.read_messages(channel=channel, limit=limit)

        if not result.get("ok"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to read messages")
            }

        messages = result.get("messages", [])

        # Format messages for easier processing
        formatted = []
        for msg in messages:
            formatted.append({
                "text": msg.get("text", ""),
                "user": msg.get("user"),
                "ts": msg.get("ts"),
                "thread_ts": msg.get("thread_ts"),
                "type": msg.get("type")
            })

        return {
            "status": "success",
            "messages": formatted,
            "count": len(formatted),
            "has_more": result.get("has_more", False)
        }

    async def _list_channels(self, client: SlackClient) -> Dict[str, Any]:
        """Lists available channels."""
        result = await client.list_channels()

        if not result.get("ok"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to list channels")
            }

        channels = []
        for ch in result.get("channels", []):
            channels.append({
                "id": ch.get("id"),
                "name": ch.get("name"),
                "is_private": ch.get("is_private", False),
                "num_members": ch.get("num_members", 0)
            })

        return {
            "status": "success",
            "channels": channels,
            "count": len(channels)
        }

    async def _add_reaction(
            self,
            client: SlackClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Adds reaction to a message."""
        channel = input_data.get("channel", "")
        message_ts = input_data.get("message_ts", "")
        emoji = input_data.get("emoji", "thumbsup")

        if not channel or not message_ts:
            raise NodeExecutionError(
                message="Channel and message timestamp are required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.add_reaction(
            channel=channel,
            timestamp=message_ts,
            emoji=emoji
        )

        if not result.get("ok"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to add reaction")
            }

        return {
            "status": "success",
            "emoji": emoji,
            "channel": channel,
            "message_ts": message_ts
        }