from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Response, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.core.database import get_db
from src.core.config import settings
from src.dao.user_dao import UserDAO
from src.api.v1.routers.workflow.deps import get_current_user, get_user_from_refresh_token
from src.models.sql.workflow.user import User
from src.services.workflow.auth_service import AuthService
from src.schemas.workflow.auth import (
    UserCreate,
    LoginRequest,
    UserResponseData,
    LoginResponseData,
    PasswordChangeRequest,
    RefreshTokenRequest,
    AuthStatusResponse,
    TokenData
)
from src.schemas.workflow.response import APIResponse


router = APIRouter()


# ============================================================
# HELPERS
# ============================================================

def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract client IP address from request.

    Handles proxies via X-Forwarded-For header.
    """
    # Check for proxy headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection
    if request.client:
        return request.client.host

    return None


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Dependency to get AuthService instance."""
    return AuthService(user_dao=UserDAO(db))


def set_auth_cookies(
        response: Response,
        access_token: str,
        refresh_token: str
) -> None:
    """
    Set authentication cookies with secure configuration.
    """
    is_secure = settings.ENVIRONMENT == "production"
    same_site = "lax" if is_secure else "lax"

    # Access token cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=is_secure,
        samesite=same_site,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

    # Refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=same_site,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth"  # Restrict to auth endpoints only
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


# ============================================================
# ENDPOINTS
# ============================================================

@router.post(
    "/register",
    response_model=APIResponse[UserResponseData],
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Create a new user account with email and password"
)
async def register(
        request: Request,
        user_in: UserCreate,
        service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user.

    - Validates email uniqueness
    - Validates password strength
    - Creates user account
    """
    # Check if registration is enabled
    if not settings.FEATURE_ENABLE_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled"
        )

    ip_address = get_client_ip(request)

    user = await service.register_user(user_in, ip_address=ip_address)

    return APIResponse(
        success=True,
        message="Registration successful",
        data=UserResponseData.model_validate(user)
    )


@router.post(
    "/login",
    response_model=APIResponse[LoginResponseData],
    summary="User login",
    description="Authenticate user and receive tokens"
)
async def login(
        request: Request,
        response: Response,
        login_data: LoginRequest,
        service: AuthService = Depends(get_auth_service)
):
    """
    Authenticate user and return tokens.

    - Validates credentials
    - Checks for account lockout
    - Returns access and refresh tokens
    - Sets secure cookies
    """
    ip_address = get_client_ip(request)

    user, access_token, refresh_token = await service.authenticate_user(
        login_data,
        ip_address=ip_address
    )

    # Set cookies
    set_auth_cookies(response, access_token, refresh_token)

    # Determine token expiry
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    if login_data.remember_me:
        expires_in = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    return APIResponse(
        success=True,
        message="Login successful",
        data=LoginResponseData(
            user=UserResponseData.model_validate(user),
            tokens=TokenData(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            ),
            expires_in=expires_in
        )
    )


@router.post(
    "/logout",
    response_model=APIResponse,
    summary="User logout",
    description="Logout and clear authentication"
)
async def logout(
        response: Response,
        current_user: Optional[User] = Depends(get_current_user)
):
    """
    Logout user and clear cookies.

    Note: For full security, implement token revocation via Redis/database.
    """
    clear_auth_cookies(response)

    return APIResponse(
        success=True,
        message="Logged out successfully"
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TokenData],
    summary="Refresh tokens",
    description="Get new access token using refresh token"
)
async def refresh_tokens(
        request: Request,
        response: Response,
        body: RefreshTokenRequest = RefreshTokenRequest(),
        db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    - Validates refresh token
    - Generates new token pair
    - Updates cookies
    """
    ip_address = get_client_ip(request)

    # Get refresh token from body or cookie
    refresh_token = body.refresh_token
    if not refresh_token:
        refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required"
        )

    # Validate and get user from refresh token
    user = await get_user_from_refresh_token(refresh_token, db)

    # Generate new tokens
    service = AuthService(user_dao=UserDAO(db))
    new_access_token, new_refresh_token = await service.refresh_tokens(
        user.id,
        ip_address=ip_address
    )

    # Update cookies
    set_auth_cookies(response, new_access_token, new_refresh_token)

    return APIResponse(
        success=True,
        message="Tokens refreshed",
        data=TokenData(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponseData],
    summary="Get current user",
    description="Get authenticated user's profile"
)
async def get_current_user_profile(
        current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's profile.
    """
    return APIResponse(
        success=True,
        message="User profile retrieved",
        data=UserResponseData.model_validate(current_user)
    )


@router.get(
    "/status",
    response_model=APIResponse[AuthStatusResponse],
    summary="Check auth status",
    description="Check if user is authenticated"
)
async def check_auth_status(
        request: Request,
        db: AsyncSession = Depends(get_db)
):
    """
    Check authentication status.

    Returns whether user is authenticated and user data if so.
    """
    from src.api.v1.routers.workflow.deps import get_current_user_optional

    user = await get_current_user_optional(request, db)

    if user:
        return APIResponse(
            success=True,
            message="Authenticated",
            data=AuthStatusResponse(
                is_authenticated=True,
                user=UserResponseData.model_validate(user)
            )
        )

    return APIResponse(
        success=True,
        message="Not authenticated",
        data=AuthStatusResponse(
            is_authenticated=False,
            user=None
        )
    )


@router.post(
    "/change-password",
    response_model=APIResponse,
    summary="Change password",
    description="Change authenticated user's password"
)
async def change_password(
        request: Request,
        body: PasswordChangeRequest,
        current_user: User = Depends(get_current_user),
        service: AuthService = Depends(get_auth_service)
):
    """
    Change user's password.

    - Validates current password
    - Validates new password strength
    - Updates password
    """
    ip_address = get_client_ip(request)

    await service.change_password(
        user_id=current_user.id,
        current_password=body.current_password,
        new_password=body.new_password,
        ip_address=ip_address
    )

    return APIResponse(
        success=True,
        message="Password changed successfully"
    )


@router.post(
    "/validate-password",
    response_model=APIResponse,
    summary="Validate password strength",
    description="Check password strength without creating account"
)
async def validate_password_strength(
        body: dict,
        service: AuthService = Depends(get_auth_service)
):
    """
    Validate password strength.

    Returns strength score and any validation errors.
    """
    password = body.get("password", "")
    email = body.get("email")

    result = await service.validate_password_strength(password, email)

    return APIResponse(
        success=True,
        message="Password validated",
        data=result
    )