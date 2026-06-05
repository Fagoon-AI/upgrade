# from loguru import logger
# from fastapi import APIRouter
# from typing import Union, Any
# from fastapi.responses import Response

# from src.models.base import ErrorResponse
# from src.models.ttv import TTVInputRequest
# from src.services.text_to_video import TextToVideoServices
# from src._exceptions import TextToVideoGenerationError


# router = APIRouter(tags=["text to video", "ttv"])


# @router.post(
#     "/video_generation",
#     response_model= Union[Any, ErrorResponse],
#     description="Async endpoint to get Text-To-Video Inference based on given input",
# )
# async def text_to_video(
#     input_request: TTVInputRequest,
# ):
#     try:
#         ttv_service = TextToVideoServices(input_request)
#         result = await ttv_service.text_to_video_creation()
#         logger.success("successfully converted from text to speech")

#         return Response(content=result, media_type="video/mp4")

#     except Exception as err:
#         logger.error(f"failed for conversion of response: {str(err)}")
#         raise TextToVideoGenerationError(details=err)
