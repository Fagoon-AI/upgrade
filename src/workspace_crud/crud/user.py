from datetime import datetime, timezone
from typing import Optional
import uuid
from src.models.sql.models import GoogleUser as SQLGoogleUser
from src.core.database.postgres import PostgresManager
from sqlalchemy import select, update, insert

class UserCRUD:
    def __init__(self, postgres_manager: PostgresManager):
        self.postgres_manager = postgres_manager

    async def get_by_google_id(self, google_id: str) -> Optional[SQLGoogleUser]:
        async with self.postgres_manager.get_session() as session:
            stmt = select(SQLGoogleUser).where(SQLGoogleUser.google_id == google_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_user(self, user_data: dict) -> SQLGoogleUser:
        async with self.postgres_manager.get_session() as session:
            if isinstance(user_data.get("system_user_id"), str):
                user_data["system_user_id"] = uuid.UUID(user_data["system_user_id"])
            
            new_user = SQLGoogleUser(**user_data)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user

    async def get_by_id(self, user_id: str) -> Optional[SQLGoogleUser]:
        async with self.postgres_manager.get_session() as session:
            stmt = select(SQLGoogleUser).where(SQLGoogleUser.system_user_id == uuid.UUID(user_id))
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[SQLGoogleUser]:
        async with self.postgres_manager.get_session() as session:
            stmt = select(SQLGoogleUser).where(SQLGoogleUser.email == email)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
