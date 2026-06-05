from loguru import logger
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.prompts import PROMPT_ENHANCER_SYSTEM_PROMPT
from src.schemas.common import SuccessResponse, FailureResponse

router = APIRouter()


class PromptRecommenderRequest(BaseModel):
    query: str


@router.post("", operation_id="enhance_prompt")
async def fagoonai_prompt_recommender(request_body: PromptRecommenderRequest):
    """
    Enhance the user prompt in descriptive manner
    """
    user_prompt_request = request_body.query
    if user_prompt_request is None:
        logger.error("User prompt is missing. Unable to process futher")
        raise ValueError("User prompt is missing")

    try:
        llm_service = LLMService(
            BaseLLMConfig(provider="openai", model="gpt-4o", max_tokens=1000)
        )
        enhanced_prompt = await llm_service.chat_completion(
            user_query=user_prompt_request, system_prompt=PROMPT_ENHANCER_SYSTEM_PROMPT
        )

        response = SuccessResponse(
            status="success",
            data={"data": enhanced_prompt},
            message="User given prompt enhanced successfully",
        )

        logger.success(f"successfully generated prompt. Enhanced prompt:\t{response}")
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Prompt generation failed: {e}")
        return JSONResponse(
            content=FailureResponse(
                status="fail",
                message="Unable to enhance the given user prompt",
                data=None,
            ).model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
