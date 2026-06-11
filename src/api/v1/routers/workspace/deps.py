from fastapi import Depends, HTTPException, status, Request
from typing import Optional, AsyncGenerator
import uuid
from src.workspace_crud.crud.user import UserCRUD
from src.workspace_crud.crud.google_token import GoogleTokenCRUD
from src.models.auth_models.user_model import UserInDB
from src.services.nosql.postgres_services import PostgresServices
from src.services.google_workspace.google_auth import GoogleAuthService
from src.core.exceptions import UnauthorizedGoogleAccess
from google.oauth2.credentials import Credentials
from loguru import logger
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.core.globals import get_db_session

async def get_google_auth_service_dep(
    request: Request
) -> GoogleAuthService:
    pg_manager = request.app.state.postgres_manager
    user_crud = UserCRUD(pg_manager)
    google_token_crud = GoogleTokenCRUD(pg_manager)
    return GoogleAuthService(user_crud, google_token_crud)

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> UserInDB:
    """
    Dependency for fetching the current user based on Authorization Bearer token or state.
    """
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization Bearer token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = credentials.credentials
    pg_manager = request.app.state.postgres_manager
    
    async with pg_manager.get_session() as session:
        pg_services = PostgresServices(session)
        try:
            sql_user = await pg_services.get_user_by_id(uuid.UUID(user_id) if len(user_id) == 36 else None)
            if sql_user:
                return UserInDB(
                    _id=str(sql_user.id),
                    name=sql_user.name,
                    email=sql_user.email,
                    password=sql_user.password_hash,
                    photo=sql_user.photo,
                    role=sql_user.role,
                    active=sql_user.active
                )
        except:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found or invalid token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_google_credentials(
        current_user: UserInDB = Depends(get_current_user),
        google_auth_service: GoogleAuthService = Depends(get_google_auth_service_dep)
) -> Credentials:
    try:
        creds = await google_auth_service.get_credentials_for_user(str(current_user.id))
        return creds
    except UnauthorizedGoogleAccess as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error("Error getting Google credentials: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve Google credentials."
        )
