from fastapi import Request, Depends, status

from src.models.auth_models.user_model import UserInDB
from src.utils.upgrade_auth.app_error import AppError

def _get_authenticated_user(request: Request) -> UserInDB:
    user = request.state.user
    if not user:
        raise AppError("You are not logged in! Please log in to get access.",
                       status_code=status.HTTP_401_UNAUTHORIZED)
    if not user.active:
        raise AppError("User account is inactive. Please contact support.",
                       status_code=status.HTTP_403_FORBIDDEN)
    return user

def restrict_to(*roles: str):
    """
    FastAPI dependency factory to restrict access based on user roles.
    """
    def role_checker(current_user: UserInDB = Depends(_get_authenticated_user)):
        if current_user.role not in roles:
            raise AppError('You do not have permission to perform this action.',
                           status_code=status.HTTP_403_FORBIDDEN)
        return current_user
    return role_checker
