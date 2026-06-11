import jwt
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple, Union, Optional
from fastapi import Response, Request, status
import secrets
import hashlib
from loguru import logger

from src.models.auth_models.user_model import UserInDB
from src.models.sql.models import RefreshToken as SQLRefreshToken
from src.core.settings import system_setting
from src.services.nosql.postgres_services import PostgresServices
from src.core.database.postgres import PostgresManager
from src.utils.upgrade_auth.app_error import AppError
from sqlalchemy.ext.asyncio import AsyncSession


async def create_access_token(user_id: str) -> str:
    """Creates a new JWT access token."""
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=system_setting.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = {
        "_id": str(user_id),
        "exp": expires.timestamp(),
        "iat": datetime.now(timezone.utc).timestamp(),
    }
    encoded_jwt = jwt.encode(
        to_encode, system_setting.JWT_SECRET, algorithm=system_setting.JWT_ALGORITHM
    )
    return encoded_jwt


async def create_refresh_token(
    user_id: str, db_services: PostgresServices
) -> Tuple[str, datetime]:
    """
    Creates a new refresh token, stores its hash and expiration in the DB,
    and returns the raw token and its expiration.
    """
    refresh_token_raw = secrets.token_urlsafe(64)
    hashed_refresh_token = hashlib.sha256(refresh_token_raw.encode("utf-8")).hexdigest()

    expires = datetime.now(timezone.utc) + timedelta(
        days=system_setting.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    try:
        token_data = {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(user_id) if len(user_id) == 36 else uuid.uuid4(),
            "token": hashed_refresh_token,
            "expires_at": expires,
            "created_at": datetime.now(timezone.utc)
        }
        new_token = SQLRefreshToken(**token_data)
        db_services.session.add(new_token)
        await db_services.session.commit()
        logger.debug(f"Refresh token for user {user_id} inserted into Postgres.")
    except Exception as e:
        await db_services.session.rollback()
        logger.error(f"Failed to save refresh token to Postgres: {e}", exc_info=True)
        raise AppError("Failed to issue refresh token.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    return refresh_token_raw, expires


async def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token_raw: str,
    access_token_expires_dt: datetime,
    refresh_token_expires_dt: datetime,
) -> None:
    """Sets the JWT access and refresh tokens as HTTP-only cookies."""

    access_max_age = int(
        (access_token_expires_dt - datetime.now(timezone.utc)).total_seconds()
    )
    refresh_max_age = int(
        (refresh_token_expires_dt - datetime.now(timezone.utc)).total_seconds()
    )

    # Mimicking your working project's environment toggles
    is_prod = system_setting.ENV.lower() not in ["development", "dev", "local"]
    
    # Always use 'none' to ensure cross-origin fetch requests work between frontend and backend.
    # Secure must be True if SameSite='none'. Chrome allows Secure cookies on http://localhost.
    samesite_val = "none"
    secure_flag = True 

    # Grab the domain from settings, defaulting to None if local
    # Make sure COOKIE_DOMAIN_1 in your .env is set to e.g., ".fagoon.ai" for production
    cookie_domain = system_setting.COOKIE_DOMAIN_1 if is_prod else None

    cookie_params = {
        "httponly": True,
        "samesite": samesite_val,
        "secure": secure_flag,
        "domain": cookie_domain,
        "path": "/",
    }

    response.set_cookie(
        key="jwt",
        value=access_token,
        expires=access_token_expires_dt,
        max_age=access_max_age,
        **cookie_params
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token_raw,
        expires=refresh_token_expires_dt,
        max_age=refresh_max_age,
        **cookie_params
    )
    
    logger.info(f"Auth cookies set. Domain: {cookie_domain}, Secure: {secure_flag}, SameSite: {samesite_val}")

async def clear_auth_cookies(response: Response):
    """Clears all authentication cookies from the root path."""
    response.delete_cookie(
        key="jwt",
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )

    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )
    logger.debug("Authentication cookies cleared.")


async def create_and_send_token(
    user: UserInDB, response: Response, request: Request
) -> str:
    """
    Creates both access and refresh tokens, sets them as cookies,
    and returns only the access token string.
    """
    postgres_manager: PostgresManager = request.app.state.postgres_manager
    if not postgres_manager:
        raise AppError("Server configuration error for token management.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    async with postgres_manager.get_session() as session:
        pg_services = PostgresServices(session)
        access_token = await create_access_token(str(user.id))
        refresh_token_raw, refresh_token_expires = await create_refresh_token(
            str(user.id), pg_services
        )

        access_token_payload = jwt.decode(
            access_token,
            system_setting.JWT_SECRET,
            algorithms=[system_setting.JWT_ALGORITHM],
        )
        access_token_expires = datetime.fromtimestamp(
            access_token_payload["exp"], tz=timezone.utc
        )

        await set_auth_cookies(
            response,
            access_token,
            refresh_token_raw,
            access_token_expires,
            refresh_token_expires,
        )

            # Log Set-Cookie headers for debugging (helps confirm cookies were added)
        try:
                set_cookie_header = response.headers.get("set-cookie")
                logger.debug(f"Set-Cookie header after token creation: {set_cookie_header}")
        except Exception:
                logger.debug("Unable to read Set-Cookie header from response for debugging.")

        return access_token


async def invalidate_all_refresh_tokens_for_user(
    user_id: str, postgres_manager: PostgresManager
):
    """
    Invalidates all refresh tokens for a given user in Postgres.
    """
    async with postgres_manager.get_session() as session:
        try:
            from sqlalchemy import delete
            stmt = delete(SQLRefreshToken).where(SQLRefreshToken.user_id == uuid.UUID(user_id))
            result = await session.execute(stmt)
            await session.commit()
            logger.info(f"Invalidated {result.rowcount} refresh tokens for user {user_id}.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to invalidate refresh tokens: {e}")
