from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from loguru import logger
from src.core.settings import system_setting

class PostgresManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
            pool_size=20,
            max_overflow=10
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    async def close(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("PostgreSQL connection pool closed.")

    def get_session(self) -> AsyncSession:
        return self.session_factory()
