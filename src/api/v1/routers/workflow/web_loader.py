from loguru import logger
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.schemas.common import SuccessResponse, FailureResponse
from src.schemas.web_loader import WebLoaderRequestModel
from src.services.web_loader import WebPageLoaderService

router = APIRouter()


@router.post(
    path="", operation_id="web_loader"
)
async def fetch_content_from_url(input_request: WebLoaderRequestModel):
    try:
        logger.info(
            "Received request to fetch content for the following URLs: {}",
            input_request.urls,
        )

        service = WebPageLoaderService(urls=input_request.urls)

        # Fetch the content asynchronously
        content = await service.get_content_from_url()

        logger.success(
            f"Successfully fetched content for {len(input_request.urls)} URL(s). "
        )

        response = SuccessResponse(
            status="success",
            message="Content fetched successfully from the provided URLs.",
            data={"content": content},
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=response.model_dump()
        )

    except Exception as e:
        logger.error(
            f"Failed to fetch content from URLs {input_request.urls}. "
            f"Error encountered: {str(e)}. Please verify the URLs or check the service."
        )

        response = FailureResponse(
            status="fail",
            message="Failed to fetch content due to an error.",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(),
        )
