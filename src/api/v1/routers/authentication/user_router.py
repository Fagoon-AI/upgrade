from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
    UploadFile,
    Form,
    Request,
    File,
)
from typing import Optional
from pydantic import EmailStr

from src.models.auth_models.user_model import (
    UserInDB,
    UserResponse,
    MeResponse,
)
from src.services.user_service import UserService
from src.utils.upgrade_auth.app_error import AppError
from src.utils.upgrade_auth.auth_utils import create_and_send_token
from src.core.database.postgres import PostgresManager


router = APIRouter()


async def get_user_service(request: Request) -> UserService:
    postgres_manager: PostgresManager = getattr(request.app.state, "postgres_manager", None)
    if not postgres_manager:
        raise RuntimeError("PostgresManager not initialized.")
    return UserService(postgres_manager)


def _get_authenticated_user(request: Request) -> UserInDB:
    user = request.state.user
    if not user:
        raise AppError(
            "You are not logged in! Please log in to get access.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.active:
        raise AppError(
            "User account is inactive. Please contact support.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


@router.get("/me", response_model=MeResponse)
async def get_me(request: Request, response: Response):
    """
    Retrieves the currently authenticated user's profile and refreshes/sends a new JWT.
    """
    current_user = _get_authenticated_user(request)
    access_token_str = await create_and_send_token(current_user, response, request)
    user_data = current_user.model_dump(by_alias=True)
    user_data.pop("password", None)
    user_data.pop("id", None)
    user_data["access"] = getattr(request.state, "access", [])
    user_data["access_token"] = access_token_str
    return MeResponse.model_validate(user_data)


@router.patch("/update-me", response_model=UserResponse)
async def update_me(
    request: Request,
    response: Response,
    user_service: UserService = Depends(get_user_service),
    name: Optional[str] = Form(None),
    email: Optional[EmailStr] = Form(None),
    bio: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    facebook: Optional[str] = Form(None),
    github: Optional[str] = Form(None),
    instagram: Optional[str] = Form(None),
    linkedin: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
):
    """Allows an authenticated user to update their profile information."""
    current_user = _get_authenticated_user(request)
    updated_user = await user_service.update_user_profile(
        current_user=current_user,
        name=name,
        email=email,
        bio=bio,
        description=description,
        facebook=facebook,
        github=github,
        instagram=instagram,
        linkedin=linkedin,
        photo=photo,
    )
    return await create_and_send_token(updated_user, response, request)


@router.delete("/delete-me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    response: Response,
    request: Request,
    user_service: UserService = Depends(get_user_service),
):
    """Allows an authenticated user to soft-delete their account."""
    current_user = _get_authenticated_user(request)
    await user_service.deactivate_user(str(current_user.id))

    # Clear JWT cookies to log out the user
    response.set_cookie(key="jwt", value="", max_age=0, path="/")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
