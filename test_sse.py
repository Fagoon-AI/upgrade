import asyncio
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting
from src.models.sql.workflow.user import User
from sqlmodel import select

async def main():
    pm = PostgresManager(system_setting.DATABASE_URL)
    async with pm.get_session() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        if user:
            print("Found user:", user.id)
            from src.utils.upgrade_auth.auth_utils import create_access_token
            token = await create_access_token(str(user.id))
            print("TOKEN:", token)
        else:
            print("No users found.")

if __name__ == "__main__":
    asyncio.run(main())
