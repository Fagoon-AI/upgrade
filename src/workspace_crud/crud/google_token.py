from datetime import datetime, timezone
from typing import Optional
import uuid
import logging
from src.models.sql.models import GoogleToken as SQLGoogleToken
from src.core.database.postgres import PostgresManager
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)

class GoogleTokenCRUD:
    def __init__(self, postgres_manager: PostgresManager):
        self.postgres_manager = postgres_manager

    async def get_by_user_id(self, user_id: str) -> Optional[SQLGoogleToken]:
        async with self.postgres_manager.get_session() as session:
            stmt = select(SQLGoogleToken).where(SQLGoogleToken.user_id == uuid.UUID(user_id))
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_token(self, token_data: dict) -> SQLGoogleToken:
        async with self.postgres_manager.get_session() as session:
            if isinstance(token_data.get("user_id"), str):
                token_data["user_id"] = uuid.UUID(token_data["user_id"])
            
            new_token = SQLGoogleToken(**token_data)
            session.add(new_token)
            await session.commit()
            await session.refresh(new_token)
            return new_token

    async def update_token(self, user_id: str, updates: dict) -> Optional[SQLGoogleToken]:
        async with self.postgres_manager.get_session() as session:
            stmt = update(SQLGoogleToken).where(SQLGoogleToken.user_id == uuid.UUID(user_id)).values(**updates)
            await session.execute(stmt)
            await session.commit()
            return await self.get_by_user_id(user_id)

    async def upsert_token(self, token_data: dict) -> SQLGoogleToken:
        async with self.postgres_manager.get_session() as session:
            if isinstance(token_data.get("user_id"), str):
                token_data["user_id"] = uuid.UUID(token_data["user_id"])
            
            token_data["updated_at"] = datetime.now(timezone.utc)
            
            # Using Postgres ON CONFLICT DO UPDATE
            stmt = insert(SQLGoogleToken).values(**token_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=[SQLGoogleToken.user_id],
                set_={k: v for k, v in token_data.items() if k != "user_id"}
            )
            await session.execute(stmt)
            await session.commit()
            return await self.get_by_user_id(str(token_data["user_id"]))
