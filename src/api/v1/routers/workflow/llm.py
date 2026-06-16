from typing import Union
from loguru import logger
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.models.llm import ChatInputRequest
from src.models.base import SuccessResponse, ErrorResponse


router = APIRouter()


@router.post(
    "",
    operation_id="chat_completion",
    response_model=Union[SuccessResponse, ErrorResponse],
    description="Async endpoint to get LLM Inference based on given input",
)
async def chat_completion(
    input_request: ChatInputRequest,
) -> Union[SuccessResponse, ErrorResponse]:
    import uuid
    api_key = None
    
    if input_request.user_id:
        from src.services.api_key_resolver import resolve_api_key
        try:
            resolved_api_key = await resolve_api_key(
                user_id=uuid.UUID(input_request.user_id),
                provider=input_request.llm_config.provider,
                feature="workflow"
            )
            if resolved_api_key:
                api_key = resolved_api_key
        except Exception as e:
            logger.error(f"Failed to resolve custom API key for workflow: {e}")

    llm_configuration = BaseLLMConfig(
        provider=input_request.llm_config.provider,
        model=input_request.llm_config.model,
        temperature=input_request.llm_config.temperature,
        max_tokens=input_request.llm_config.max_tokens,
        top_p=input_request.llm_config.top_p,
        api_key=api_key,
    )

    try:
        llm_services = LLMService(llm_configuration)

        response = await llm_services.chat_completion(
            user_query=input_request.user_prompt,
            system_prompt=input_request.system_prompt,
        )
        logger.success("response generated successfully")

        result = SuccessResponse(
            status="success",
            message=f"Successfully performed chat completion using {input_request.llm_config.model} model",
            data={"result": response},
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=result.model_dump()
        )

    except Exception as err:
        result = ErrorResponse(
            status="fail",
            data=None,
            message="An error occurred while getting response from llm",
        )

        logger.error("failed to generate response: {}: {}", result.model_dump(), err)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=result.model_dump(),
        )
