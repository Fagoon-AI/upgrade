import asyncio
from sqlalchemy import text
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting

async def add_token_column():
    print("Starting database migration to add 'token' column to 'users' table...")
    if not system_setting.DATABASE_URL:
        print("Error: DATABASE_URL not found in settings.")
        return

    db_manager = PostgresManager(system_setting.DATABASE_URL)
    try:
        async with db_manager.get_session() as session:
            # Check if column exists first to be safe
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='token';
            """)
            result = await session.execute(check_sql)
            if result.fetchone():
                print("Column 'token' already exists in 'users' table.")
            else:
                print("Adding 'token' column to 'users' table...")
                alter_sql = text("ALTER TABLE users ADD COLUMN token VARCHAR(255);")
                await session.execute(alter_sql)
                await session.commit()
                print("Successfully added 'token' column.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await db_manager.close()

if __name__ == "__main__":
    asyncio.run(add_token_column())
