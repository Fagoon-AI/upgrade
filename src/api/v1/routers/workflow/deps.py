# ... (Keep all the imports and token extractors at the top the same) ...
from typing import Optional, Annotated, Literal
from uuid import UUID
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status, Depends, Header
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.core.config import settings
from src.core.security import ALGORITHM
from src.core.database import get_db
from src.models.sql.workflow.user import User


# ============================================================
# TOKEN TYPES
# ============================================================

class TokenType:
    """Token type constants."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"


# ============================================================
# TOKEN EXTRACTION
# ============================================================

class TokenExtractor:
    """
    Extracts JWT tokens from requests.
    """

    async def __call__(self, request: Request) -> Optional[str]:
        """
        Extract token from request.
        """
        token = None

        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            elif len(parts) == 1:
                token = parts[0]

        if not token:
            cookie_token = request.cookies.get("access_token") or request.cookies.get("jwt")
            if cookie_token:
                if cookie_token.startswith("Bearer "):
                    token = cookie_token[7:]
                else:
                    token = cookie_token

        return token


class RefreshTokenExtractor:
    """Extracts refresh tokens from cookies."""

    async def __call__(self, request: Request) -> Optional[str]:
        """Extract refresh token from cookie."""
        return request.cookies.get("refresh_token")


extract_token = TokenExtractor()
extract_refresh_token = RefreshTokenExtractor()


# ============================================================
# USER RETRIEVAL DEPENDENCIES
# ============================================================

async def get_current_user(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    FastAPI dependency for getting the current authenticated user.
    Leverages AuthMiddleware's validation and syncs to the workflow `user` table.
    """
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    current_app_user = getattr(request.state, "user", None)
    if not current_app_user:
        raise unauthorized_error

    import uuid
    try:
        uid = uuid.UUID(current_app_user.id)
    except Exception:
        raise unauthorized_error

    query = select(User).where(User.id == uid)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        user = User(
            id=uid,
            email=current_app_user.email,
            hashed_password="[synced_from_users_table]",
            full_name=current_app_user.name,
            is_active=current_app_user.active
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to sync user to workflow user table: {e}")
            raise HTTPException(status_code=500, detail="User sync failed")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


async def get_current_user_optional(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)]
) -> Optional[User]:
    """
    Optional user dependency - returns None if not authenticated.
    """
    current_app_user = getattr(request.state, "user", None)
    if not current_app_user:
        return None

    import uuid
    try:
        uid = uuid.UUID(current_app_user.id)
    except Exception:
        return None

    query = select(User).where(User.id == uid)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        user = User(
            id=uid,
            email=current_app_user.email,
            hashed_password="[synced_from_users_table]",
            full_name=current_app_user.name,
            is_active=current_app_user.active
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
        except Exception as e:
            await db.rollback()
            return None

    return user


async def get_current_superuser(
        current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Dependency for superuser-only endpoints.

    Usage:
        @app.delete("/admin/users/{user_id}")
        async def delete_user(
            user_id: UUID,
            admin: User = Depends(get_current_superuser)
        ):
            ...
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


async def get_user_from_refresh_token(
        refresh_token: Annotated[Optional[str], Depends(extract_refresh_token)],
        db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    Gets user from refresh token for token refresh flow.

    IMPORTANT: This validates that the token is a REFRESH token,
    not an access token. This is the SEC-004 fix in action.

    Usage:
        @app.post("/auth/refresh")
        async def refresh_tokens(
            user: User = Depends(get_user_from_refresh_token)
        ):
            # Generate new access token
            ...
    """
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not refresh_token:
        raise unauthorized_error

    # Validate token - MUST be "refresh" type
    try:
        payload = validate_token(refresh_token, expected_type=TokenType.REFRESH)
    except HTTPException:
        raise unauthorized_error

    # Lookup user
    query = select(User).where(User.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalars().first()

    if user is None:
        raise unauthorized_error

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


# ============================================================
# API KEY AUTHENTICATION (OPTIONAL EXTENSION)
# ============================================================

async def get_user_from_api_key(
        x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
        db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional API key authentication.

    Checks X-API-Key header for server-to-server communication.

    Note: This requires an api_keys table to be implemented.
    Returns None if not implemented or key not provided.

    Usage:
        @app.get("/api/data")
        async def get_data(
            user: User = Depends(get_user_from_api_key_or_token)
        ):
            ...
    """
    if not x_api_key:
        return None

    # TODO: Implement API key lookup
    # This would require an ApiKey model with user_id foreign key
    # For now, return None to fall back to JWT auth

    logger.debug("API key authentication not implemented")
    return None


async def get_user_from_api_key_or_token(
        api_key_user: Annotated[Optional[User], Depends(get_user_from_api_key)],
        token_user: Annotated[Optional[User], Depends(get_current_user_optional)]
) -> User:
    """
    Supports both API key and JWT authentication.

    Priority:
    1. API key (X-API-Key header)
    2. JWT token (Authorization header or cookie)

    Usage:
        @app.get("/api/data")
        async def get_data(user: User = Depends(get_user_from_api_key_or_token)):
            ...
    """
    user = api_key_user or token_user

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user