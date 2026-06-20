from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any

from src.models.sql.workflow.user import User
from src.api.v1.routers.workflow.deps import get_current_user

router = APIRouter()

# In-memory fallback if no DB column exists yet
_MOCK_PREFS: Dict[str, dict] = {}

class UserPreferencesResponse(BaseModel):
    success: bool = True
    data: dict

@router.get("", response_model=UserPreferencesResponse)
async def get_user_preferences(request: Request, current_user: User = Depends(get_current_user)):
    user_id_str = str(current_user.id)
    prefs = _MOCK_PREFS.get(user_id_str, {
        "theme": "light",
        "responseTone": "professional",
        "systemPrompt": "",
        "nickname": current_user.full_name,
        "bio": "",
        "location": "",
        "role": "user"
    })
    return UserPreferencesResponse(data=prefs)

@router.post("", response_model=UserPreferencesResponse)
async def update_user_preferences(request: Request, body: dict, current_user: User = Depends(get_current_user)):
    user_id_str = str(current_user.id)
    existing = _MOCK_PREFS.get(user_id_str, {})
    existing.update(body)
    _MOCK_PREFS[user_id_str] = existing
    return UserPreferencesResponse(data=existing)
