import time
from loguru import logger
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.schemas.support_bot import (
    InputRequestBody,
    SupportBotResponseModel,
    ResponseEnum,
)

from src.services.support_bot.support_bot_service import SupportBotService
from src.prompts import (
    CAREER_GATEWAY_SUPPORT_BOT_SYSTEM_PROMPT,
    CAREER_GATEWAY_SUPPORT_BOT_FAILED_RESPONSE,
)
from src.constants import CAREER_GATEWAY_SUPPORT_BOT_COLLECTION_NAME

router = APIRouter()


@router.post(path="/career-gateway/bot")
async def support_bot(input_request: InputRequestBody):
    start_time = time.perf_counter()

    user_query = input_request.query
    if not user_query:
        logger.error("User query is missing")
        raise Exception("User query is empty")

    try:
        bot_service = SupportBotService(
            collection_name=CAREER_GATEWAY_SUPPORT_BOT_COLLECTION_NAME,
        )

        response = await bot_service.get_answer_from_support_bot(
            user_query=user_query,
            system_prompt=CAREER_GATEWAY_SUPPORT_BOT_SYSTEM_PROMPT,
            fallback_handle_response=CAREER_GATEWAY_SUPPORT_BOT_FAILED_RESPONSE,
        )

        logger.success(
            f"Successfully generated response for user query: {user_query}"
            f"Total time taken is: {time.perf_counter() - start_time}"
        )

        return JSONResponse(
            content=SupportBotResponseModel(
                status=ResponseEnum.SUCCESS.value,
                data=response,
                error_details=None,
            ).model_dump(),
            status_code=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(
            f"Error occurred while preparing response from support bot: {str(e)}"
            f"Total time taken is: {time.perf_counter() - start_time}"
        )

        return JSONResponse(
            content=SupportBotResponseModel(
                status=ResponseEnum.FAILED.value, data=None, error_details=str(e)
            ).model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
