from datetime import datetime, timezone
from typing import Optional, Dict, Any
import os
import asyncio
import uuid
from PIL import Image
from io import BytesIO
from loguru import logger

from src.models.auth_models.user_model import UserInDB, UserResponse
from src.utils.upgrade_auth.app_error import AppError
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from fastapi import status, UploadFile


# Define a directory for user photos
USER_PHOTO_DIR = "public/img/users"
os.makedirs(USER_PHOTO_DIR, exist_ok=True)
DEFAULT_AVATAR = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Male_Avatar.jpg/800px-Male_Avatar.jpg"


class UserService:
    def __init__(self, postgres_manager: PostgresManager):
        self.postgres_manager = postgres_manager

    async def get_user_profile(self, user_id: str) -> UserInDB:
        """Retrieves a user's profile by ID from PostgreSQL."""
        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            sql_user = await pg_services.get_user_by_id(uuid.UUID(user_id))
            if not sql_user:
                raise AppError("User profile not found.", status_code=status.HTTP_404_NOT_FOUND)
            
            return UserInDB(
                _id=str(sql_user.id),
                name=sql_user.name,
                email=sql_user.email,
                password=sql_user.password_hash,
                photo=sql_user.photo,
                role=sql_user.role,
                active=sql_user.active,
                verified=sql_user.verified,
                social_media=sql_user.social_media,
                password_changed_at=sql_user.password_changed_at
            )

    async def update_user_profile(
        self,
        current_user: UserInDB,
        name: Optional[str] = None,
        email: Optional[str] = None,
        bio: Optional[str] = None,
        description: Optional[str] = None,
        facebook: Optional[str] = None,
        github: Optional[str] = None,
        instagram: Optional[str] = None,
        linkedin: Optional[str] = None,
        photo: Optional[UploadFile] = None,
    ) -> UserInDB:
        """Updates a user's profile information in PostgreSQL."""
        update_data: Dict[str, Any] = {}

        for field, value in [
            ("name", name),
            ("email", email),
            ("bio", bio),
            ("description", description),
        ]:
            if value is not None:
                update_data[field] = value

        social_media_updates = {
            k: v
            for k, v in {
                "facebook": facebook,
                "github": github,
                "instagram": instagram,
                "linkedin": linkedin,
            }.items()
            if v is not None
        }
        if social_media_updates:
            new_sm = {**current_user.social_media, **social_media_updates}
            update_data["social_media"] = new_sm

        if photo:
            # (Image processing logic remains same, but uses PostgreSQL user ID)
            if not photo.content_type or not photo.content_type.startswith("image"):
                 raise AppError("File is not a valid image.", status_code=status.HTTP_400_BAD_REQUEST)

            photo_filename = f"user-{current_user.id}-{datetime.now(timezone.utc).timestamp():.0f}.jpeg"
            photo_path = os.path.join(USER_PHOTO_DIR, photo_filename)

            async def process_and_save_image():
                contents = await photo.read()
                img = Image.open(BytesIO(contents)).resize((500, 500), Image.Resampling.LANCZOS)
                img.save(photo_path, format="JPEG", quality=90)

            await asyncio.to_thread(process_and_save_image)
            update_data["photo"] = photo_filename

        if not update_data:
            return current_user

        async with self.postgres_manager.get_session() as session:
            from src.models.sql.models import User as SQLUser
            from sqlalchemy import update as sqlalchemy_update
            
            # Map password field back to password_hash if it were in update_data
            if "password" in update_data:
                update_data["password_hash"] = update_data.pop("password")

            stmt = sqlalchemy_update(SQLUser).where(SQLUser.id == uuid.UUID(str(current_user.id))).values(**update_data)
            await session.execute(stmt)
            await session.commit()
            
            return await self.get_user_profile(str(current_user.id))

    async def deactivate_user(self, user_id: str) -> bool:
        """Soft-deactivates a user's account in PostgreSQL."""
        async with self.postgres_manager.get_session() as session:
            from src.models.sql.models import User as SQLUser
            from sqlalchemy import update as sqlalchemy_update
            stmt = sqlalchemy_update(SQLUser).where(SQLUser.id == uuid.UUID(user_id)).values(active=False)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
