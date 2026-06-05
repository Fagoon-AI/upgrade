from typing import Optional, AsyncGenerator
from src.services.nosql.postgres_services import PostgresServices
from src.core.database.postgres import PostgresManager
from src.utils.upgrade_auth.app_error import AppError
from fastapi import status, Request

async def get_db_session(request: Request) -> AsyncGenerator:
    """
    FastAPI dependency that provides a PostgreSQL async session.
    """
    postgres_manager: Optional[PostgresManager] = getattr(request.app.state, "postgres_manager", None)
    if postgres_manager is None:
        raise AppError(
            "PostgresManager not initialized in app.state.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    
    async with postgres_manager.get_session() as session:
        yield session

async def get_postgres_services(request: Request) -> AsyncGenerator[PostgresServices, None]:
    """
    FastAPI dependency that provides a PostgresServices instance with an active session.
    """
    postgres_manager: Optional[PostgresManager] = getattr(request.app.state, "postgres_manager", None)
    if postgres_manager is None:
        raise AppError(
            "PostgresManager not initialized in app.state.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    async with postgres_manager.get_session() as session:
        yield PostgresServices(session)
