import asyncio
import uuid
import bcrypt
from datetime import datetime, timezone
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.core.settings import system_setting

async def create_user_if_not_exists(pg_services, name, email, raw_password, role="user"):
    existing_user = await pg_services.get_user_by_email(email)
    if existing_user:
        print(f"User {email} already exists.")
        return existing_user

    print(f"Creating user {email}...")
    hashed_pw = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    user_data = {
        "id": uuid.uuid4(),
        "name": name,
        "email": email,
        "password_hash": hashed_pw,
        "role": role,
        "verified": True,
        "active": True,
        "visited": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "social_media": {}
    }
    
    new_user = await pg_services.create_user(user_data)
    print(f"Created {email} successfully!")
    return new_user

async def main():
    db_url = system_setting.DATABASE_URL
    print(f"Connecting to database: {db_url}")
    
    postgres_manager = PostgresManager(db_url)
    async with postgres_manager.get_session() as session:
        pg_services = PostgresServices(session)
        
        # Create admin
        await create_user_if_not_exists(pg_services, "Fagoon Admin", "admin@fagoon.ai", "adminpassword123", "admin")
        # Create chris@fagoondigital.com
        await create_user_if_not_exists(pg_services, "Chris Fagoon", "chris@fagoondigital.com", "Chris@123", "admin")

if __name__ == "__main__":
    asyncio.run(main())
