from loguru import logger
from fastapi import APIRouter, status, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.schemas.text_to_speech import TTSApiRequest, TTSRequestWithUserId, BaseTTSConfig
from src.services.tts import TextToSpeechServices
from src.schemas.common import SuccessResponse, FailureResponse

router = APIRouter()


@router.post(
    "",
    description="Converts text to speech based on the provided data, supporting both direct user_id and middleware-based authentication.",
    summary="Dynamic Text-to-Speech",
    response_model=SuccessResponse
)
async def text_to_speech(request: Request):
    """
    Handles TTS requests by dynamically determining the input structure.

    This endpoint can handle two types of JSON payloads:
    1. With `user_id` included in the request body.
    2. Without `user_id`, relying on middleware to provide the user context.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    user_id: str
    prompt: str
    config: BaseTTSConfig

    try:
        if "user_id" in payload:
            validated_data = TTSRequestWithUserId.model_validate(payload)
            user_id = validated_data.user_id
            prompt = validated_data.user_prompt
            config = validated_data.tts_config
        else:
            validated_data = TTSApiRequest.model_validate(payload)
            prompt = validated_data.prompt
            config = validated_data.config

            if not hasattr(request.state, "user") or not request.state.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required. User context not found.",
                )
            user_id = request.state.user.id

    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())

    try:
        tts_service = TextToSpeechServices(config=config)
        audio_data = await tts_service.convert_text_to_speech_and_get_url(
            user_id=str(user_id),
            prompt=prompt,
            voice_id=config.voice_id,
            model=config.model,
        )

        response = SuccessResponse(
            status="success",
            message="Successfully converted text into speech.",
            data=audio_data,
        )
        return JSONResponse(content=response.model_dump(), status_code=status.HTTP_201_CREATED)

    except ValueError as ve:
        logger.warning(f"Bad request in TTS endpoint for user '{user_id}': {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as err:
        logger.error(f"Failed TTS conversion for user '{user_id}': {err}", exc_info=True)
        response = FailureResponse(
            status="fail",
            message="An error occurred while converting text into speech.",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(),
        )