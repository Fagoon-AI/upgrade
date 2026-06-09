from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import RedirectResponse, JSONResponse
from loguru import logger
import uuid
from src.core.settings import system_setting
from src.core.exceptions import UnauthorizedGoogleAccess
from src.services.nosql.postgres_services import PostgresServices
from src.workspace_crud.crud.google_token import GoogleTokenCRUD
from src.workspace_crud.crud.user import UserCRUD
from src.schemas.workspace.auth import GoogleUserDetails
from src.schemas.common import SuccessResponse, FailureResponse
from src.schemas.workspace.common import GoogleAuthURL
from src.services.google_workspace.google_auth import GoogleAuthService
from src.core.globals import get_postgres_services
from src.models.sql.models import GoogleUser as SQLGoogleUser
from sqlalchemy import insert

router = APIRouter()

async def get_google_auth_service(request: Request) -> GoogleAuthService:
    pg_manager = request.app.state.postgres_manager
    user_crud = UserCRUD(pg_manager)
    google_token_crud = GoogleTokenCRUD(pg_manager)
    return GoogleAuthService(user_crud, google_token_crud)

@router.get("/google/login", response_model=GoogleAuthURL)
async def google_login(google_auth_service: GoogleAuthService = Depends(get_google_auth_service)):
    try:
        auth_url = await google_auth_service.get_authorization_url()
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error("Error generating Google auth URL: {}", e)
        raise HTTPException(status_code=500, detail="Could not initiate Google authentication.")

@router.get("/google/callback", response_class=RedirectResponse)
async def google_callback(
    code: str = Query(...),
    google_auth_service: GoogleAuthService = Depends(get_google_auth_service),
):
    try:
        token_info = await google_auth_service.exchange_code_for_token(code)
        redirect_url = f"{system_setting.FRONTEND_REDIRECT_URI}/{token_info['google_id']}"
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        logger.error("Google OAuth callback failed: {}", e)
        return RedirectResponse(url=f"{system_setting.FRONTEND_REDIRECT_URI}?error=auth_failed", status_code=302)

@router.post("/save")
async def save_user_details(
    request: Request,
    input_request: GoogleUserDetails,
):
    pg_manager = request.app.state.postgres_manager
    async with pg_manager.get_session() as session:
        try:
            # Check if exists
            from sqlalchemy import select
            stmt = select(SQLGoogleUser).where(SQLGoogleUser.google_id == input_request.google_id)
            res = await session.execute(stmt)
            if res.scalar_one_or_none():
                return SuccessResponse(status="success", message="Already linked", data={})

            new_g_user = SQLGoogleUser(
                id=uuid.uuid4(),
                google_id=input_request.google_id,
                system_user_id=uuid.UUID(input_request.system_user_id),
                email=input_request.email or "unknown@gmail.com",
            )
            session.add(new_g_user)
            await session.commit()
            return SuccessResponse(status="success", message="Linked successfully", data={})
        except Exception as e:
            logger.error("Failed to link Google user: {}", e)
            return JSONResponse(status_code=400, content={"detail": "Link failed"})
