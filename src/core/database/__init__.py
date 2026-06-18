"""Compatibility bridge for workflow database imports."""
from typing import AsyncGenerator, Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database.postgres import PostgresManager


# Singleton reference (set during app startup)
_manager: Optional[PostgresManager] = None
SessionLocal = None


def set_manager(manager: PostgresManager):
    global _manager, SessionLocal
    _manager = manager
    SessionLocal = manager.session_factory


def get_database_manager() -> PostgresManager:
    if _manager is None:
        raise RuntimeError("Database not initialized. Call set_manager() at startup.")
    return _manager


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a DB session from request.app.state.postgres_manager."""
    postgres_manager = getattr(request.app.state, "postgres_manager", None)
    if postgres_manager is None:
        raise RuntimeError("PostgresManager not initialized in app.state.")
    async with postgres_manager.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
