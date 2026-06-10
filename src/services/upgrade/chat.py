import asyncio
import base64
import json
from datetime import datetime, timezone
from loguru import logger
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from src.models.sql.models import UpgradeChatHistory, UpgradeChat
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.services.document_processor import DocumentProcessor
from sqlalchemy import select, update

class UpgradeChatService:
    def __init__(self, postgres_manager: PostgresManager, document_processor: DocumentProcessor):
        self.postgres_manager = postgres_manager
        self.document_processor = document_processor

    async def create_upgrade_conversation(self, user_id: str, title: Optional[str] = None) -> str:
        async with self.postgres_manager.get_session() as session:
            history = UpgradeChatHistory(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                title=title or "New Upgrade Chat",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(history)
            await session.commit()
            return str(history.id)

    async def store_user_research_request(self, conversation_id: str, task: str):
        # In SQL, we can either create the history if it doesn't exist or add a message
        async with self.postgres_manager.get_session() as session:
            try:
                hist_id = uuid.UUID(conversation_id)
            except:
                return # Should handle better

            message = UpgradeChat(
                id=uuid.uuid4(),
                history_id=hist_id,
                role="user",
                content=task,
                created_at=datetime.now(timezone.utc)
            )
            session.add(message)
            await session.commit()

    async def store_research_report_as_chat(self, research_data: Dict[str, Any]):
        conversation_id = research_data.get("research_id")
        async with self.postgres_manager.get_session() as session:
            try:
                hist_id = uuid.UUID(conversation_id)
            except:
                return

            message = UpgradeChat(
                id=uuid.uuid4(),
                history_id=hist_id,
                role="assistant",
                content=research_data.get("report_content", ""),
                extra_metadata={
                    "research_images": research_data.get("research_images", []),
                    "source_urls": research_data.get("source_urls", []),
                    "visited_urls": research_data.get("visited_urls", []),
                    "costs": research_data.get("research_costs", 0)
                },
                created_at=datetime.now(timezone.utc)
            )
            session.add(message)
            
            # Update history title if needed
            stmt = update(UpgradeChatHistory).where(UpgradeChatHistory.id == hist_id).values(updated_at=datetime.now(timezone.utc))
            await session.execute(stmt)
            
            await session.commit()

    async def get_upgrade_history(self, history_id: str) -> List[Dict[str, Any]]:
        async with self.postgres_manager.get_session() as session:
            stmt = select(UpgradeChat).where(UpgradeChat.history_id == uuid.UUID(history_id)).order_by(UpgradeChat.created_at.asc())
            result = await session.execute(stmt)
            messages = result.scalars().all()
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.extra_metadata,
                    "created_at": msg.created_at.isoformat()
                } for msg in messages
            ]

    async def prepare_messages_with_system_prompt(
        self, conversation_history: List[Dict[str, Any]], preferences: Any
    ) -> List[Dict[str, Any]]:
        """
        Formats the raw conversation history for the LLM and prepends a system prompt.
        """
        messages = []
        
        # Determine the system prompt from preferences or use a default
        system_prompt = getattr(preferences, "system_prompt", None)
        if not system_prompt:
            system_prompt = "You are a helpful, harmless, and honest AI assistant."

        # Add the system prompt first
        messages.append({"role": "system", "content": system_prompt})

        # Append the rest of the conversation history
        for msg in conversation_history:
            # Filter out UI-only metadata if necessary, keeping just role and content
            formatted_msg = {
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            }
            messages.append(formatted_msg)

        return messages

    async def write_upgrade_message(
        self,
        insert_message: Union[List[Dict[str, Any]], str],
        conversation_id: str,
        role: str,
    ) -> bool:
        async with self.postgres_manager.get_session() as session:
            try:
                hist_id = uuid.UUID(conversation_id)
            except Exception as e:
                logger.error(f"Invalid conversation_id: {e}")
                return False

            content = ""
            metadata = []
            if isinstance(insert_message, list):
                for item in insert_message:
                    if item.get("type") == "chat":
                        content += item.get("data", "")
                    else:
                        metadata.append(item)
            else:
                content = str(insert_message)

            # Ensure role is stored as a plain string (handle Enums passed in)
            role_value = getattr(role, "value", None) if role is not None else None
            if role_value is None:
                role_value = str(role)

            message = UpgradeChat(
                id=uuid.uuid4(),
                history_id=hist_id,
                role=role_value,
                content=content,
                extra_metadata={"data": metadata} if metadata else {},
                created_at=datetime.now(timezone.utc)
            )
            session.add(message)
            
            stmt = update(UpgradeChatHistory).where(UpgradeChatHistory.id == hist_id).values(updated_at=datetime.now(timezone.utc))
            await session.execute(stmt)
            
            await session.commit()
            return True
