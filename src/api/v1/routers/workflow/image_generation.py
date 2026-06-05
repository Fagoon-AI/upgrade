from loguru import logger
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.services.imagen import ImageGenerationService
from src.models.diffusion import ImageGenerationInputRequest

from src.schemas.diffusion import BaseDiffusionConfig
from src.schemas.common import SuccessResponse, FailureResponse


router = APIRouter()


@router.post(
    "",
    operation_id="generate_workflow_image",
    description="Async endpoint for image generation based on given input",
)
async def generate_image_for_workflow(input_request: ImageGenerationInputRequest):
    try:
        image_services = ImageGenerationService(
            BaseDiffusionConfig(
                provider=input_request.diffusion_model_config.provider,
            )
        )
        image_file_path = await image_services.generate_image(
            user_id=input_request.user_id,
            prompt=input_request.prompt,
            negative_prompt=input_request.negative_prompt,
            model=input_request.diffusion_model_config.model,
            height=input_request.diffusion_model_config.height,
            width=input_request.diffusion_model_config.width,
        )

        response = SuccessResponse(
            status="success",
            message="Successfully generated an image",
            data={"file_path": image_file_path},
        )

        logger.success(f"response generated successfully: {response.model_dump()}")
        return JSONResponse(
            content=response.model_dump(), status_code=status.HTTP_200_OK
        )

    except Exception as err:
        response = FailureResponse(
            status="fail",
            message="Failed to generate an image",
            data=None,
        )
        logger.error(f"failed to generate response: {response.model_dump()}: {str(err)}")
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
