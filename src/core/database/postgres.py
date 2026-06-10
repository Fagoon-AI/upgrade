import socket
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from loguru import logger
from src.core.settings import system_setting

# --- Monkey-Patch to Force IPv4 ---
# This fixes connection timeouts on Windows machines where IPv6 is 
# preferred by asyncio but blocked by the ISP/Router.
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [res for res in responses if res[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# ----------------------------------

class PostgresManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
            pool_size=20,
            max_overflow=10,
            connect_args={"timeout": 60}
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
