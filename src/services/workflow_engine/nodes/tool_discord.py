"""
Discord Integration Node.

Enterprise-grade Discord API integration for messaging, embeds, and webhooks.
"""

import asyncio
import json
import re
from typing import Dict, Any, List, Optional
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
class DiscordConfig:
    """Configuration for Discord operations."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_message_length: int = 2000
    max_embed_description: int = 4096
    max_embeds_per_message: int = 10


# Discord API base URL
DISCORD_API_BASE = "https://discord.com/api/v10"

# Rate limit codes
RATE_LIMIT_CODES = [429]

# Retryable status codes
RETRYABLE_CODES = [500, 502, 503, 504, 429]


# ============================================================
# EMBED BUILDER
# ============================================================

class DiscordEmbedBuilder:
    """
    Builds Discord embed objects with validation.
    """

    def __init__(self):
        self._embed: Dict[str, Any] = {}

    def set_title(self, title: str, url: Optional[str] = None) -> "DiscordEmbedBuilder":
        """Sets embed title."""
        self._embed["title"] = title[:256]  # Discord limit
        if url:
            self._embed["url"] = url
        return self

    def set_description(self, description: str) -> "DiscordEmbedBuilder":
        """Sets embed description."""
        self._embed["description"] = description[:4096]  # Discord limit
        return self

    def set_color(self, color: int) -> "DiscordEmbedBuilder":
        """Sets embed color (decimal or hex)."""
        self._embed["color"] = color
        return self

    def set_color_hex(self, hex_color: str) -> "DiscordEmbedBuilder":
        """Sets embed color from hex string."""
        hex_color = hex_color.lstrip("#")
        self._embed["color"] = int(hex_color, 16)
        return self

    def set_author(
            self,
            name: str,
            url: Optional[str] = None,
            icon_url: Optional[str] = None
    ) -> "DiscordEmbedBuilder":
        """Sets embed author."""
        self._embed["author"] = {"name": name[:256]}
        if url:
            self._embed["author"]["url"] = url
        if icon_url:
            self._embed["author"]["icon_url"] = icon_url
        return self

    def set_footer(
            self,
            text: str,
            icon_url: Optional[str] = None
    ) -> "DiscordEmbedBuilder":
        """Sets embed footer."""
        self._embed["footer"] = {"text": text[:2048]}
        if icon_url:
            self._embed["footer"]["icon_url"] = icon_url
        return self

    def set_thumbnail(self, url: str) -> "DiscordEmbedBuilder":
        """Sets embed thumbnail."""
        self._embed["thumbnail"] = {"url": url}
        return self

    def set_image(self, url: str) -> "DiscordEmbedBuilder":
        """Sets embed image."""
        self._embed["image"] = {"url": url}
        return self

    def add_field(
            self,
            name: str,
            value: str,
            inline: bool = False
    ) -> "DiscordEmbedBuilder":
        """Adds a field to the embed."""
        if "fields" not in self._embed:
            self._embed["fields"] = []

        if len(self._embed["fields"]) < 25:  # Discord limit
            self._embed["fields"].append({
                "name": name[:256],
                "value": value[:1024],
                "inline": inline
            })
        return self

    def set_timestamp(self, timestamp: Optional[datetime] = None) -> "DiscordEmbedBuilder":
        """Sets embed timestamp."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        self._embed["timestamp"] = timestamp.isoformat()
        return self

    def build(self) -> Dict[str, Any]:
        """Returns the built embed."""
        return self._embed

    @classmethod
    def workflow_notification(
            cls,
            title: str,
            description: str,
            status: str = "info",
            workflow_name: Optional[str] = None,
            execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a standard workflow notification embed."""
        color_map = {
            "info": 0x3498DB,     # Blue
            "success": 0x2ECC71,  # Green
            "warning": 0xF39C12,  # Orange
            "error": 0xE74C3C,    # Red
        }
        emoji_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }

        builder = cls()
        builder.set_title(f"{emoji_map.get(status, '📋')} {title}")
        builder.set_description(description)
        builder.set_color(color_map.get(status, 0x3498DB))

        if workflow_name:
            builder.add_field("Workflow", workflow_name, inline=True)
        if execution_id:
            builder.add_field("Execution", execution_id[:8], inline=True)

        builder.set_timestamp()
        builder.set_footer("Workflow Platform")

        return builder.build()


# ============================================================
# DISCORD CLIENT
# ============================================================

class DiscordClient:
    """
    Robust Discord API client with retry logic.
    """

    def __init__(
            self,
            token: Optional[str] = None,
            webhook_url: Optional[str] = None,
            config: Optional[DiscordConfig] = None
    ):
        self.token = token
        self.webhook_url = webhook_url
        self.config = config or DiscordConfig()

    def _get_headers(self) -> Dict[str, str]:
        """Gets API headers for bot requests."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bot {self.token}"
        return headers

    async def _make_request(
            self,
            method: str,
            url: str,
            data: Optional[Dict[str, Any]] = None,
            use_auth: bool = True
    ) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        headers = self._get_headers() if use_auth else {"Content-Type": "application/json"}

        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers)
                    elif method.upper() == "POST":
                        response = await client.post(url, headers=headers, json=data)
                    elif method.upper() == "PATCH":
                        response = await client.patch(url, headers=headers, json=data)
                    elif method.upper() == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    # Handle rate limiting
                    if response.status_code in RATE_LIMIT_CODES:
                        retry_after = float(response.headers.get("Retry-After", 5))
                        logger.warning(f"Discord rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle retryable errors
                    if response.status_code in RETRYABLE_CODES and attempt < self.config.max_retries:
                        logger.warning(f"Discord API error {response.status_code}. Retrying...")
                        await asyncio.sleep(self.config.retry_delay * attempt)
                        continue

                    # Success responses
                    if response.status_code in [200, 201, 204]:
                        if response.status_code == 204:
                            return {"success": True}
                        result = response.json()
                        result["success"] = True
                        return result

                    # Error responses
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", f"HTTP {response.status_code}")
                    except:
                        error_msg = f"HTTP {response.status_code}"

                    return {"success": False, "error": error_msg}

            except httpx.TimeoutException:
                last_error = "Request timeout"
                logger.warning(f"Discord request timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Discord connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Discord request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "max_retries_exceeded"}

    # ============================================================
    # WEBHOOK OPERATIONS
    # ============================================================

    async def send_webhook_message(
            self,
            content: Optional[str] = None,
            embeds: Optional[List[Dict]] = None,
            username: Optional[str] = None,
            avatar_url: Optional[str] = None,
            thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends a message via webhook."""
        if not self.webhook_url:
            return {"success": False, "error": "Webhook URL not configured"}

        payload: Dict[str, Any] = {}

        if content:
            payload["content"] = content[:self.config.max_message_length]

        if embeds:
            payload["embeds"] = embeds[:self.config.max_embeds_per_message]

        if username:
            payload["username"] = username[:80]

        if avatar_url:
            payload["avatar_url"] = avatar_url

        url = self.webhook_url
        if thread_id:
            url = f"{url}?thread_id={thread_id}"

        return await self._make_request("POST", url, data=payload, use_auth=False)

    # ============================================================
    # BOT OPERATIONS
    # ============================================================

    async def send_message(
            self,
            channel_id: str,
            content: Optional[str] = None,
            embeds: Optional[List[Dict]] = None,
            reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends a message to a channel via bot."""
        if not self.token:
            return {"success": False, "error": "Bot token not configured"}

        payload: Dict[str, Any] = {}

        if content:
            payload["content"] = content[:self.config.max_message_length]

        if embeds:
            payload["embeds"] = embeds[:self.config.max_embeds_per_message]

        if reply_to:
            payload["message_reference"] = {"message_id": reply_to}

        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
        return await self._make_request("POST", url, data=payload)

    async def get_channel(self, channel_id: str) -> Dict[str, Any]:
        """Gets channel information."""
        url = f"{DISCORD_API_BASE}/channels/{channel_id}"
        return await self._make_request("GET", url)

    async def get_messages(
            self,
            channel_id: str,
            limit: int = 50,
            before: Optional[str] = None,
            after: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gets messages from a channel."""
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages?limit={min(limit, 100)}"
        if before:
            url += f"&before={before}"
        if after:
            url += f"&after={after}"

        return await self._make_request("GET", url)

    async def add_reaction(
            self,
            channel_id: str,
            message_id: str,
            emoji: str
    ) -> Dict[str, Any]:
        """Adds a reaction to a message."""
        # URL encode the emoji
        import urllib.parse
        encoded_emoji = urllib.parse.quote(emoji)

        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        return await self._make_request("PUT", url, data={})

    async def create_thread(
            self,
            channel_id: str,
            message_id: str,
            name: str,
            auto_archive_duration: int = 1440  # 24 hours
    ) -> Dict[str, Any]:
        """Creates a thread from a message."""
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/threads"
        payload = {
            "name": name[:100],
            "auto_archive_duration": auto_archive_duration
        }
        return await self._make_request("POST", url, data=payload)

    async def get_guild_channels(self, guild_id: str) -> Dict[str, Any]:
        """Gets all channels in a guild."""
        url = f"{DISCORD_API_BASE}/guilds/{guild_id}/channels"
        return await self._make_request("GET", url)


# ============================================================
# DISCORD NODE
# ============================================================

class DiscordNode(BaseNode):
    """
    Enterprise-Grade Discord Integration Node.

    Features:
    - Webhook message sending
    - Bot message operations
    - Rich embed support
    - Reaction handling
    - Thread creation
    - Retry with exponential backoff
    - Rate limit handling

    Operations:
    - send_webhook: Send message via webhook
    - send_message: Send message via bot
    - get_messages: Get channel messages
    - add_reaction: Add reaction to message
    - create_thread: Create thread from message
    """

    node_type = "discordNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Discord",
            "icon": "MessageSquare",
            "category": "Communication",
            "description": "Full Discord integration with webhooks, bots, and embeds.",
            "fields": [
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": [
                        "send_webhook",
                        "send_message",
                        "get_messages",
                        "add_reaction",
                        "create_thread"
                    ],
                    "default": "send_webhook"
                },
                {
                    "name": "auth_method",
                    "label": "Authentication",
                    "type": "select",
                    "options": ["webhook", "bot_token"],
                    "default": "webhook"
                },
                {
                    "name": "webhook_url",
                    "label": "Webhook URL",
                    "type": "text",
                    "conditional": {"auth_method": "webhook"},
                    "placeholder": "https://discord.com/api/webhooks/...",
                    "helper": "Discord webhook URL"
                },
                {
                    "name": "connection_id",
                    "label": "Discord Bot Connection",
                    "type": "connection_select",
                    "provider": "DISCORD",
                    "conditional": {"auth_method": "bot_token"}
                },
                {
                    "name": "channel_id",
                    "label": "Channel ID",
                    "type": "text",
                    "conditional": {"auth_method": "bot_token"},
                    "placeholder": "123456789012345678",
                    "helper": "Discord channel ID"
                },
                {
                    "name": "content",
                    "label": "Message Content",
                    "type": "textarea",
                    "conditional": {"operation": ["send_webhook", "send_message"]},
                    "helper": "Plain text message content"
                },
                {
                    "name": "use_embed",
                    "label": "Use Embed",
                    "type": "boolean",
                    "default": False,
                    "conditional": {"operation": ["send_webhook", "send_message"]}
                },
                {
                    "name": "embed_title",
                    "label": "Embed Title",
                    "type": "text",
                    "conditional": {"use_embed": True}
                },
                {
                    "name": "embed_description",
                    "label": "Embed Description",
                    "type": "textarea",
                    "conditional": {"use_embed": True}
                },
                {
                    "name": "embed_color",
                    "label": "Embed Color",
                    "type": "text",
                    "placeholder": "#3498DB",
                    "default": "#3498DB",
                    "conditional": {"use_embed": True},
                    "helper": "Hex color code"
                },
                {
                    "name": "embed_status",
                    "label": "Notification Type",
                    "type": "select",
                    "options": ["info", "success", "warning", "error"],
                    "default": "info",
                    "conditional": {"use_embed": True}
                },
                {
                    "name": "embed_fields",
                    "label": "Embed Fields (JSON)",
                    "type": "code",
                    "language": "json",
                    "conditional": {"use_embed": True},
                    "helper": '[{"name": "Field", "value": "Value", "inline": true}]'
                },
                {
                    "name": "username",
                    "label": "Override Username",
                    "type": "text",
                    "conditional": {"operation": "send_webhook"},
                    "helper": "Custom webhook username"
                },
                {
                    "name": "avatar_url",
                    "label": "Override Avatar URL",
                    "type": "text",
                    "conditional": {"operation": "send_webhook"},
                    "helper": "Custom avatar image URL"
                },
                {
                    "name": "message_id",
                    "label": "Message ID",
                    "type": "text",
                    "conditional": {"operation": ["add_reaction", "create_thread"]},
                    "helper": "Target message ID"
                },
                {
                    "name": "emoji",
                    "label": "Emoji",
                    "type": "text",
                    "placeholder": "👍",
                    "conditional": {"operation": "add_reaction"},
                    "helper": "Emoji to react with"
                },
                {
                    "name": "thread_name",
                    "label": "Thread Name",
                    "type": "text",
                    "conditional": {"operation": "create_thread"}
                },
                {
                    "name": "message_limit",
                    "label": "Message Limit",
                    "type": "number",
                    "default": 50,
                    "conditional": {"operation": "get_messages"}
                }
            ],
            "outputs": ["status", "message_id", "messages", "count", "thread_id"]
        }

    def __init__(self):
        super().__init__()
        self.config = DiscordConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Discord operation."""
        operation = input_data.get("operation", "send_webhook")
        auth_method = input_data.get("auth_method", "webhook")

        # Get client
        client = await self._get_client(db, input_data, auth_method)

        # Execute operation
        if operation == "send_webhook":
            return await self._send_webhook(client, input_data, context)
        elif operation == "send_message":
            return await self._send_message(client, input_data, context)
        elif operation == "get_messages":
            return await self._get_messages(client, input_data)
        elif operation == "add_reaction":
            return await self._add_reaction(client, input_data)
        elif operation == "create_thread":
            return await self._create_thread(client, input_data)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_client(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any],
            auth_method: str
    ) -> DiscordClient:
        """Gets authenticated Discord client."""
        if auth_method == "webhook":
            webhook_url = input_data.get("webhook_url", "").strip()
            if not webhook_url:
                raise NodeExecutionError(
                    message="Webhook URL is required",
                    node_type=self.node_type,
                    retryable=False
                )

            # Validate webhook URL
            if not re.match(r'^https://discord\.com/api/webhooks/\d+/.+$', webhook_url):
                raise NodeExecutionError(
                    message="Invalid Discord webhook URL",
                    node_type=self.node_type,
                    retryable=False
                )

            return DiscordClient(webhook_url=webhook_url, config=self.config)

        else:
            # Bot token from connection
            connection_id = input_data.get("connection_id")

            if not connection_id:
                raise NodeExecutionError(
                    message="Connection ID is required for bot operations",
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
                    provider="discord"
                )

            try:
                creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                token = creds.get("bot_token") or creds.get("access_token")
            except Exception as e:
                raise ConnectionError(
                    message="Failed to decrypt credentials",
                    node_type=self.node_type,
                    provider="discord"
                )

            if not token:
                raise ConnectionError(
                    message="Connection missing bot token",
                    node_type=self.node_type,
                    provider="discord"
                )

            return DiscordClient(token=token, config=self.config)

    def _build_embeds(
            self,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Optional[List[Dict]]:
        """Builds embed objects from input data."""
        if not input_data.get("use_embed"):
            return None

        title = input_data.get("embed_title", "Workflow Notification")
        description = input_data.get("embed_description", "")
        color = input_data.get("embed_color", "#3498DB")
        status = input_data.get("embed_status", "info")

        # Use the workflow notification builder
        if status:
            embed = DiscordEmbedBuilder.workflow_notification(
                title=title,
                description=description,
                status=status,
                execution_id=context.execution_id
            )
        else:
            builder = DiscordEmbedBuilder()
            builder.set_title(title)
            builder.set_description(description)

            if color:
                try:
                    builder.set_color_hex(color)
                except:
                    builder.set_color(0x3498DB)

            builder.set_timestamp()
            embed = builder.build()

        # Add custom fields
        fields_str = input_data.get("embed_fields", "").strip()
        if fields_str:
            try:
                fields = json.loads(fields_str)
                if "fields" not in embed:
                    embed["fields"] = []
                for field in fields[:25]:  # Discord limit
                    embed["fields"].append({
                        "name": str(field.get("name", ""))[:256],
                        "value": str(field.get("value", ""))[:1024],
                        "inline": bool(field.get("inline", False))
                    })
            except json.JSONDecodeError:
                logger.warning("Invalid embed fields JSON")

        return [embed]

    async def _send_webhook(
            self,
            client: DiscordClient,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Sends message via webhook."""
        content = input_data.get("content", "").strip()
        embeds = self._build_embeds(input_data, context)
        username = input_data.get("username")
        avatar_url = input_data.get("avatar_url")

        if not content and not embeds:
            raise NodeExecutionError(
                message="Content or embed is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.send_webhook_message(
            content=content if content else None,
            embeds=embeds,
            username=username,
            avatar_url=avatar_url
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Webhook send failed")
            }

        return {
            "status": "success",
            "message_id": result.get("id"),
            "method": "webhook"
        }

    async def _send_message(
            self,
            client: DiscordClient,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Sends message via bot."""
        channel_id = input_data.get("channel_id", "").strip()
        content = input_data.get("content", "").strip()
        embeds = self._build_embeds(input_data, context)

        if not channel_id:
            raise NodeExecutionError(
                message="Channel ID is required",
                node_type=self.node_type,
                retryable=False
            )

        if not content and not embeds:
            raise NodeExecutionError(
                message="Content or embed is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.send_message(
            channel_id=channel_id,
            content=content if content else None,
            embeds=embeds
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Message send failed")
            }

        return {
            "status": "success",
            "message_id": result.get("id"),
            "channel_id": result.get("channel_id"),
            "method": "bot"
        }

    async def _get_messages(
            self,
            client: DiscordClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets channel messages."""
        channel_id = input_data.get("channel_id", "").strip()
        limit = int(input_data.get("message_limit", 50))

        if not channel_id:
            raise NodeExecutionError(
                message="Channel ID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.get_messages(channel_id=channel_id, limit=limit)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to get messages")
            }

        # Format messages - result is a list when successful
        messages = []
        if isinstance(result, list):
            for msg in result:
                messages.append({
                    "id": msg.get("id"),
                    "content": msg.get("content"),
                    "author": {
                        "id": msg.get("author", {}).get("id"),
                        "username": msg.get("author", {}).get("username")
                    },
                    "timestamp": msg.get("timestamp"),
                    "embeds": msg.get("embeds", [])
                })

        return {
            "status": "success",
            "messages": messages,
            "count": len(messages)
        }

    async def _add_reaction(
            self,
            client: DiscordClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Adds reaction to message."""
        channel_id = input_data.get("channel_id", "").strip()
        message_id = input_data.get("message_id", "").strip()
        emoji = input_data.get("emoji", "👍").strip()

        if not channel_id or not message_id:
            raise NodeExecutionError(
                message="Channel ID and Message ID are required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.add_reaction(
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to add reaction")
            }

        return {
            "status": "success",
            "emoji": emoji,
            "message_id": message_id
        }

    async def _create_thread(
            self,
            client: DiscordClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates thread from message."""
        channel_id = input_data.get("channel_id", "").strip()
        message_id = input_data.get("message_id", "").strip()
        thread_name = input_data.get("thread_name", "").strip()

        if not channel_id or not message_id or not thread_name:
            raise NodeExecutionError(
                message="Channel ID, Message ID, and Thread Name are required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.create_thread(
            channel_id=channel_id,
            message_id=message_id,
            name=thread_name
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to create thread")
            }

        return {
            "status": "success",
            "thread_id": result.get("id"),
            "thread_name": result.get("name")
        }
