from loguru import logger
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi import status

from src.constants import MODEL_CARD_FILE_PATH
from src.schemas.common import SuccessResponse, FailureResponse
from src.services.agents.llm_model import get_available_model_list

router = APIRouter(prefix="")


@router.get("", response_class=JSONResponse, operation_id="list_available_models")
async def get_available_models():
    """
    Endpoint to retrieve the list of model names from the model card YAML file.
    """
    try:
        logger.info("Fetching the list of available models from the model card.")

        available_models = get_available_model_list(MODEL_CARD_FILE_PATH)

        if not available_models:
            logger.warning("No models were found in the model card.")
            response = FailureResponse(
                status="fail",
                data=None,
                message="Oops! We couldn't find any models in the model card.",
            )
            return JSONResponse(
                content=response.model_dump(),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        response = SuccessResponse(
            status="success",
            data={"models": available_models},
            message="The available models were successfully retrieved.",
        )

        logger.success("The available models were successfully retrieved.")
        return JSONResponse(
            content=response.model_dump(), status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"An error occurred while fetching the available models: {e}")
        response = FailureResponse(
            status="fail", data=None, message=f"An unexpected error occurred: {e}"
        )
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
