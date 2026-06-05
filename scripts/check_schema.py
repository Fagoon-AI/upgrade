import asyncio
from sqlalchemy import text
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting

async def check_schema():
    if not system_setting.DATABASE_URL:
        print("Error: DATABASE_URL not found in settings.")
        return

    db_manager = PostgresManager(system_setting.DATABASE_URL)
    try:
        async with db_manager.get_session() as session:
            sql = text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name='users';
            """)
            result = await session.execute(sql)
            columns = result.fetchall()
            print("Columns in 'users' table:")
            for col in columns:
                print(f" - {col[0]} ({col[1]})")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await db_manager.close()

if __name__ == "__main__":
    asyncio.run(check_schema())
