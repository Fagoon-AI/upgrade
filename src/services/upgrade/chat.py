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
