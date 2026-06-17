import uuid
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, status

from src.schemas.workspace.ai import GenerateTextRequest, GenerateTextResponse
from src.services.google_workspace.ai_service import AIService
from src.api.v1.routers.workspace.deps import get_current_user
from src.models.auth_models.user_model import UserInDB

router = APIRouter()


async def get_ai_service_dep(current_user: UserInDB = Depends(get_current_user)) -> AIService:
    user_uuid = uuid.UUID(str(current_user.id)) if current_user else None
    return AIService(user_id=user_uuid)


@router.post(
    "/generate-text",
    response_model=GenerateTextResponse,
    summary="Generate text based on a prompt using AI",
)
async def generate_text(
    request: GenerateTextRequest, ai_service: AIService = Depends(get_ai_service_dep)
):
    """
    Generates text content based on a user-provided prompt using the configured AI model.
    """
    try:
        generated_text = await ai_service.generate_text_from_prompt(request.prompt)
        return GenerateTextResponse(generated_text=generated_text)
    except Exception as e:
        logger.error("Error generating text from prompt: {}", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during AI text generation.",
        )
