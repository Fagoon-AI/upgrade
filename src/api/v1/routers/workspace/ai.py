from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, status

from src.schemas.workspace.ai import GenerateTextRequest, GenerateTextResponse
from src.schemas.workspace.gmail import SummarizeEmailRequest, SummarizeEmailResponse
from src.services.google_workspace.ai_service import AIService

router = APIRouter()


async def get_ai_service_dep() -> AIService:
    return AIService()


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
        logger.error(f"Error generating text from prompt: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during AI text generation.",
        )
