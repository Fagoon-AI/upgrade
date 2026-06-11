import asyncio
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from src.agents.agent_manager import AgentManager
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting
from src.services.agents.chat import AgentChatService
from src.services.agents.chat_orchestrator import ChatOrchestrator
from src.services.channel_adapter.channel_config_service import get_channel_config
from src.schemas.llm import BaseLLMConfig
from src.storages.file_storage import FileStorageService
from src.storages.vectordb_storages.pgvector import PgVectorStorage


async def process_webhook_event(event: Dict[str, Any]) -> None:
    if not system_setting.DATABASE_URL:
        logger.error("DATABASE_URL is not configured. Cannot process webhook event.")
        return

    pg_manager = PostgresManager(system_setting.DATABASE_URL)
    file_storage = FileStorageService()
    agent_manager = AgentManager(pg_manager, file_storage)
    chat_service = AgentChatService(pg_manager)
    vector_store = PgVectorStorage(pg_manager, vector_dim=1536)
    orchestrator = ChatOrchestrator(agent_manager, vector_store, chat_service)

    llm_config = BaseLLMConfig(
        model=event.get("model", system_setting.SMART_MODEL_ID),
        provider=system_setting.SMART_MODEL_PROVIDER,
        temperature=event.get("temperature", 0.1),
        top_p=event.get("top_p", 0.9),
    )

    response_text = ""
    try:
        async for token in orchestrator.stream_chat(
            user_id=event["owner_user_id"],
            agent_id=event["agent_id"],
            history_id=event["history_id"],
            message=event["text"],
            llm_config=llm_config,
        ):
            response_text += token

        logger.info("Webhook event processed for channel {}, agent {}. Response length: {}", event["channel"], event["agent_id"], len(response_text))

        agent = await agent_manager.get_agent(event["agent_id"])
        channel_config = get_channel_config(agent.get("channel_integration", {}), event["channel"]) if agent else {}

        await send_channel_reply(
            channel=event["channel"],
            recipient_id=event["sender_id"],
            text=response_text,
            metadata=event.get("metadata", {}),
            channel_config=channel_config,
        )

    except Exception as e:
        logger.error("Failed to process webhook event for {}: {}", event, e, exc_info=True)
    finally:
        await pg_manager.close()


async def send_channel_reply(
    channel: str,
    recipient_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    channel_config: Optional[Dict[str, Any]] = None,
) -> bool:
    metadata = metadata or {}
    if not text:
        logger.warning("No response text to send back for channel {}.", channel)
        return False

    channel_config = channel_config or {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        if channel == "whatsapp":
            phone_number_id = channel_config.get("phone_number_id") or system_setting.WHATSAPP_PHONE_NUMBER_ID
            access_token = channel_config.get("access_token") or system_setting.WHATSAPP_ACCESS_TOKEN
            if not phone_number_id or not access_token:
                logger.warning("WhatsApp reply skipped because WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN is not configured.")
                return False
            url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "text",
                "text": {"body": text},
            }
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            response = await client.post(url, json=payload, headers=headers)
            logger.info("WhatsApp reply status {} for recipient {}", response.status_code, recipient_id)
            return response.is_success

        if channel == "messenger":
            page_token = channel_config.get("page_access_token") or system_setting.FACEBOOK_PAGE_ACCESS_TOKEN
            if not page_token:
                logger.warning("Facebook Messenger reply skipped because FACEBOOK_PAGE_ACCESS_TOKEN is not configured.")
                return False
            url = f"https://graph.facebook.com/v17.0/me/messages?access_token={page_token}"
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": text},
            }
            response = await client.post(url, json=payload)
            logger.info("Messenger reply status {} for recipient {}", response.status_code, recipient_id)
            return response.is_success

        if channel == "telegram":
            bot_token = channel_config.get("bot_token") or system_setting.TELEGRAM_BOT_TOKEN
            if not bot_token:
                logger.warning("Telegram reply skipped because TELEGRAM_BOT_TOKEN is not configured.")
                return False
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": recipient_id, "text": text}
            response = await client.post(url, json=payload)
            logger.info("Telegram reply status {} for chat {}", response.status_code, recipient_id)
            return response.is_success

    logger.warning("No channel reply implementation found for {}.", channel)
    return False
