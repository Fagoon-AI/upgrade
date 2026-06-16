import asyncio
import uuid
import bcrypt
import os
from datetime import datetime, timezone
from sqlalchemy import select
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.core.settings import system_setting

async def main():
    db_url = system_setting.DATABASE_URL
    print(f"Connecting to database: {db_url}")
    
    postgres_manager = PostgresManager(db_url)
    async with postgres_manager.get_session() as session:
        pg_services = PostgresServices(session)
        
        # Check if user already exists
        email = "admin@fagoon.ai"
        existing_user = await pg_services.get_user_by_email(email)
        
        if existing_user:
            print(f"Default admin user already exists: {email}")
            print(f"User ID: {existing_user.id}")
        else:
            print(f"Creating default admin user: {email}...")
            raw_password = "adminpassword123"
            hashed_pw = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            
            user_data = {
                "id": uuid.uuid4(),
                "name": "Fagoon Admin",
                "email": email,
                "password_hash": hashed_pw,
                "role": "admin",
                "verified": True,
                "active": True,
                "visited": 1,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "social_media": {}
            }
            
            new_user = await pg_services.create_user(user_data)
            print("=========================================")
            print("Default admin user created successfully!")
            print(f"Email: {email}")
            print(f"Password: {raw_password}")
            print(f"User ID: {new_user.id}")
            print("=========================================")

if __name__ == "__main__":
    asyncio.run(main())
