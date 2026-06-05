import json
from loguru import logger
from fastapi import APIRouter, status, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from src.services.stt import SpeechToTextService
from src.schemas.common import SuccessResponse, FailureResponse
from src.schemas.speech_to_text import BaseSTTConfig

router = APIRouter()

@router.post(
    "",
    operation_id="speech_to_text_transcription",
    summary="Transcribe audio to text via file upload",
    description="Receives an audio file and its configuration via multipart/form-data and returns the transcribed text.",
    response_model=SuccessResponse
)
async def speech_to_text(
        config: str = Form(..., description="A JSON string representing the BaseSTTConfig."),
        file: UploadFile = File(..., description="The audio file to be transcribed.")
):
    """
    Handles STT requests by reading an uploaded audio file and transcribing it.
    """
    try:
        # Parse the configuration string into a Pydantic model
        stt_config = BaseSTTConfig(**json.loads(config))
        stt_service = SpeechToTextService(stt_config)

        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot process empty audio file.")

        transcribed_data = await stt_service.convert_speech_to_text(
            audio=audio_bytes,
            language=stt_config.language,
            temperature=stt_config.temperature
        )

        response = SuccessResponse(
            status="success",
            message="Successfully converted speech to text",
            data={"transcription": transcribed_data},
        )
        return JSONResponse(content=response.model_dump(), status_code=status.HTTP_200_OK)

    except json.JSONDecodeError:
        logger.warning("Failed to decode STT config JSON string.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid format for STT configuration.")
    except ValueError as ve:
        logger.warning(f"Bad request in speech-to-text: {ve}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as err:
        logger.error(f"Failed speech-to-text conversion: {err}", exc_info=True)
        response = FailureResponse(
            status="fail",
            message="An error occurred while converting speech into text.",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(),
        )