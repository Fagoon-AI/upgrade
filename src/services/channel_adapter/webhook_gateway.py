import hashlib
import hmac
import json
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, HTTPException
from loguru import logger
import uuid

from src.agents.agent_manager import AgentManager
from src.core.settings import system_setting
from src.services.agents.chat import AgentChatService
from src.services.channel_adapter.channel_config_service import (
    get_channel_config,
    merge_channel_config,
)
from src.services.channel_adapter.processor import process_webhook_event


class WebhookGatewayService:
    def __init__(
        self,
        agent_manager: AgentManager,
        chat_service: AgentChatService,
        cache_client: Optional[Any] = None,
        queue: Any = None,
    ):
        self.agent_manager = agent_manager
        self.chat_service = chat_service
        if cache_client is None:
            from src.services.cache.memory_cache import MemoryCache
            self.cache = MemoryCache()
        else:
            self.cache = cache_client
        self.queue = queue

    async def _get_agent_channel_config(self, agent_id: str, channel: str) -> Dict[str, Any]:
        if not self.agent_manager:
            raise HTTPException(status_code=500, detail="Agent manager is not available.")

        agent = await self.agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found.")

        return get_channel_config(agent.get("channel_integration", {}), channel)

    async def _set_channel_verified(self, agent_id: str, channel: str) -> None:
        agent = await self.agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found.")

        agent_config = agent.get("channel_integration", {}) or {}
        channel_config = get_channel_config(agent_config, channel)
        if channel_config.get("verified"):
            return

        channel_config["verified"] = True
        agent_config[channel] = merge_channel_config(agent_config, channel, channel_config)[channel]
        await self.agent_manager.update_agent(agent_id, {"channel_integration": agent_config})

    async def _verify_signature(self, channel: str, agent_id: str, headers: Dict[str, str], body: bytes) -> None:
        if channel in {"whatsapp", "messenger"}:
            # Normalize headers to lowercase to handle case-insensitive lookup
            normalized_headers = {k.lower(): v for k, v in headers.items()}
            signature_header = normalized_headers.get("x-hub-signature-256", "")
            
            if not signature_header:
                raise HTTPException(status_code=403, detail="Missing signature header.")

            config = await self._get_agent_channel_config(agent_id, channel)
            secret = config.get("app_secret")
            if not secret:
                raise HTTPException(status_code=403, detail="Webhook secret is not configured.")

            expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            
            # --- FORCE LOGGING TO INFO ---
            logger.info(f"Header Signature: {signature_header}")
            logger.info(f"Calculated Signature: {expected}")
            # -----------------------------

            if not hmac.compare_digest(signature_header, expected):
                raise HTTPException(status_code=403, detail="Invalid webhook signature.")

        elif channel == "telegram":
            token_header = headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            config = await self._get_agent_channel_config(agent_id, channel)
            secret_token = config.get("webhook_secret_token") or system_setting.TELEGRAM_BOT_SECRET_TOKEN
            if not token_header or token_header != secret_token:
                raise HTTPException(status_code=403, detail="Invalid Telegram secret token.")
        else:
            raise HTTPException(status_code=404, detail=f"Unsupported channel: {channel}")

    def _normalize_payload(self, channel: str, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if channel == "whatsapp":
            entry = payload.get("entry", [])
            if not entry:
                raise HTTPException(status_code=400, detail="Missing WhatsApp payload entry.")
            change = entry[0].get("changes", [])
            if not change:
                raise HTTPException(status_code=400, detail="Missing WhatsApp change list.")
            value = change[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                raise HTTPException(status_code=200, detail="No WhatsApp message to process.")
            message = messages[0]
            text = None
            if message.get("type") == "text":
                text = message.get("text", {}).get("body")
            return {
                "channel": channel,
                "agent_id": agent_id,
                "message_id": message.get("id"),
                "sender_id": message.get("from"),
                "text": text,
                "metadata": {"platform": "whatsapp", "raw": payload},
            }

        if channel == "messenger":
            entry = payload.get("entry", [])
            if not entry:
                raise HTTPException(status_code=400, detail="Missing Messenger payload entry.")
            messaging = entry[0].get("messaging", [])
            if not messaging:
                raise HTTPException(status_code=400, detail="Missing Messenger messaging array.")
            message_event = messaging[0]
            message = message_event.get("message", {})
            return {
                "channel": channel,
                "agent_id": agent_id,
                "message_id": message.get("mid"),
                "sender_id": message_event.get("sender", {}).get("id"),
                "text": message.get("text"),
                "metadata": {"platform": "messenger", "raw": payload},
            }

        if channel == "telegram":
            message = payload.get("message") or payload.get("edited_message")
            if not message:
                raise HTTPException(status_code=400, detail="Missing Telegram message payload.")
            return {
                "channel": channel,
                "agent_id": agent_id,
                "message_id": str(message.get("message_id")),
                "sender_id": str(message.get("from", {}).get("id")),
                "text": message.get("text"),
                "metadata": {"platform": "telegram", "raw": payload},
            }

        raise HTTPException(status_code=404, detail=f"Unsupported channel: {channel}")

    async def _is_duplicate(self, channel: str, agent_id: str, message_id: str) -> bool:
        if not message_id:
            return False
        key = f"webhook:dedup:{channel}:{agent_id}:{message_id}"
        if await self.cache.exists(key):
            logger.info("Duplicate webhook event skipped: {}", key)
            return True
        await self.cache.set(key, "1", ex=86400)
        return False

    async def _get_or_create_history_id(self, channel: str, agent_id: str, sender_id: str) -> str:
        session_key = f"webhook:session:{channel}:{agent_id}:{sender_id}"
        session_data = await self.cache.get_json(session_key)
        if session_data and session_data.get("history_id"):
            return session_data["history_id"]

        agent = await self.agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found.")

        owner_user_id = agent.get("user_id")
        logger.info(f"Retrieved owner_user_id for agent {agent_id}: {owner_user_id} (type: {type(owner_user_id)})")
        
        # --- FIX: Robust UUID validation ---
        try:
            user_uuid = uuid.UUID(str(owner_user_id))
        except (ValueError, TypeError):
            logger.error(f"Invalid owner_user_id: {owner_user_id}. Cannot convert to UUID.")
            raise HTTPException(status_code=500, detail="Agent owner user ID is not a valid UUID.")
        # -----------------------------------

        history_id = await self.chat_service.create_conversation(
            str(user_uuid),
            agent_id,
            title=f"{channel.title()} Conversation",
        )
        await self.cache.set_json(session_key, {"history_id": history_id}, ex=86400)
        return history_id

    async def _enqueue_event(self, event: Dict[str, Any], background_tasks: BackgroundTasks) -> None:
        try:
            if self.queue:
                self.queue.enqueue("process_webhook_message_task", event)
                logger.info("Webhook event dispatched to App State Queue for async processing.")
            else:
                logger.info("No queue configured. Falling back to in-process background task.")
                background_tasks.add_task(process_webhook_event, event)
        except Exception as e:
            logger.warning("Queue dispatch failed, falling back to in-process background task: {}", e)
            background_tasks.add_task(process_webhook_event, event)

    async def handle_webhook(
        self,
        channel: str,
        agent_id: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        body: bytes,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, Any]:
        logger.info(f"handle_webhook started for channel={channel}, agent_id={agent_id}")
        try:
            await self._verify_signature(channel, agent_id, headers, body)
            logger.info("Signature verification passed.")
        except HTTPException as e:
            logger.error(f"Signature verification failed: {e.detail}")
            raise

        normalized = self._normalize_payload(channel, agent_id, payload)
        if not normalized.get("text"):
            raise HTTPException(status_code=200, detail="No text message found to process.")

        if await self._is_duplicate(channel, agent_id, normalized["message_id"]):
            return {"status": "duplicate", "message_id": normalized["message_id"]}

        normalized["history_id"] = await self._get_or_create_history_id(
            channel,
            agent_id,
            normalized["sender_id"],
        )

        agent = await self.agent_manager.get_agent(agent_id)
        normalized["owner_user_id"] = agent.get("user_id")

        await self._enqueue_event(normalized, background_tasks)
        return {"status": "accepted", "message_id": normalized["message_id"]}

    async def verify_subscription(
        self,
        channel: str,
        agent_id: str,
        hub_mode: str,
        hub_verify_token: str,
        hub_challenge: str,
    ) -> str:
        if channel not in {"whatsapp", "messenger"}:
            raise HTTPException(status_code=404, detail=f"Subscription verification is not supported for channel: {channel}")

        channel_config = await self._get_agent_channel_config(agent_id, channel)
        verify_token = channel_config.get("verify_token")

        logger.info(
            "Verifying subscription: channel=%s agent_id=%s hub_mode=%s hub_verify_token=%s stored_verify_token=%s",
            channel,
            agent_id,
            hub_mode,
            hub_verify_token,
            verify_token,
        )

        if not verify_token or hub_mode != "subscribe" or hub_verify_token != verify_token:
            raise HTTPException(status_code=403, detail="Webhook verification failed.")

        if verify_token == channel_config.get("verify_token"):
            await self._set_channel_verified(agent_id, channel)

        return hub_challenge
