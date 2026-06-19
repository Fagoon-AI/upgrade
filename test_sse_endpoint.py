import asyncio
import httpx
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting
from src.models.sql.workflow.user import User
from sqlmodel import select

async def main():
    pm = PostgresManager(system_setting.DATABASE_URL)
    async with pm.get_session() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        if not user:
            print("No users found.")
            return

        from src.utils.upgrade_auth.auth_utils import create_access_token
        token = await create_access_token(str(user.id))
        
    url = f"http://localhost:8000/api/v1/streams?channel=exec_trace:test&access_token={token}"
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("GET", url) as response:
                print("Status:", response.status_code)
                print("Headers:", response.headers)
                async for line in response.aiter_lines():
                    print("Line:", line)
                    break # Just want to see if it connects successfully
        except Exception as e:
            print("Exception:", e)

if __name__ == "__main__":
    asyncio.run(main())
