from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from src.schemas.vibe_coder_schemas import CodeGenerationRequest, CodeGenerationResponse
from src.services.vibe_coder.code_generation import UIPrototyperService
from src.core.database import get_db
from src.api.v1.routers.workspace.deps import get_current_user
from src.models.auth_models.user_model import UserInDB
from src.models.sql.models import LLMModelConfig

router = APIRouter(prefix="/vibe", tags=["Vibe UI Prototyper"])

# Dependency injection for the service
def get_ui_prototyper_service() -> UIPrototyperService:
    return UIPrototyperService()

async def get_user_llm_config_by_id(db: AsyncSession, user_id: str, config_id: str) -> LLMModelConfig:
    """Helper to fetch a specific LLM config for a user."""
    result = await db.execute(
        select(LLMModelConfig).where(
            LLMModelConfig.id == config_id,
            LLMModelConfig.user_id == user_id,
            LLMModelConfig.is_deleted == False
        )
    )
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=400, detail="LLM configuration must be added and selected before starting Vibe Code Mode.")
    return config

@router.post("/generate", response_model=CodeGenerationResponse)
async def generate_ui_component(
    request: CodeGenerationRequest,
    service: UIPrototyperService = Depends(get_ui_prototyper_service),
    db: AsyncSession = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Generate a React/Tailwind UI component based on a prompt.
    Returns the raw code block for the frontend to render.
    """
    try:
        user_llm_config = await get_user_llm_config_by_id(db, str(current_user.id), request.llm_config_id)
        
        response = await service.generate_ui_code(request, user_llm_config)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate UI code: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate UI component.")

@router.post("/generate/stream")
async def stream_ui_component(
    request: CodeGenerationRequest,
    service: UIPrototyperService = Depends(get_ui_prototyper_service),
    db: AsyncSession = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    """
    Generate a React/Tailwind UI component based on a prompt.
    Streams the raw code block tokens for the frontend to render in real-time.
    """
    try:
        user_llm_config = await get_user_llm_config_by_id(db, str(current_user.id), request.llm_config_id)
        
        return StreamingResponse(
            service.stream_ui_code(request, user_llm_config),
            media_type="text/event-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream UI code: {e}")
        raise HTTPException(status_code=500, detail="Failed to stream UI component.")