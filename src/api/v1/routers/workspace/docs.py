from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from .deps import get_google_credentials
from src.schemas.workspace.common import Message
from src.schemas.workspace.docs import (CreateDocRequest, DocContentResponse, DocDetails,
                              WriteDocRequest)
from src.services.google_workspace.google_docs import GoogleDocsService


router = APIRouter()

async def get_docs_service(
    credentials: Credentials = Depends(get_google_credentials),
) -> GoogleDocsService:
    return GoogleDocsService(credentials)


@router.post(
    "/create",
    response_model=DocDetails,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Google Docs document",
)
async def create_google_doc(
    request: CreateDocRequest,
    docs_service: GoogleDocsService = Depends(get_docs_service),
):
    """
    Creates a new Google Docs document with a specified title and optional initial content.
    """
    try:
        doc = await docs_service.create_document(
            title=request.title, initial_content=request.initial_content
        )
        return DocDetails(**doc)
    except HttpError as e:
        logger.error(
            f"Docs API error creating document: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to create Google Doc: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error creating document: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating document.",
        )


@router.get(
    "/{document_id}/content",
    response_model=DocContentResponse,
    summary="Get plain text content of a Google Docs document",
)
async def get_google_doc_content(
    document_id: str, docs_service: GoogleDocsService = Depends(get_docs_service)
):
    """
    Retrieves the plain text content of a Google Docs document.
    """
    try:
        full_doc = await docs_service.get_document_content(document_id)
        content_text = await docs_service.extract_text_from_document(document_id)

        return DocContentResponse(
            document_id=document_id,
            title=full_doc.get("title", "Untitled Document"),
            content=content_text,
        )
    except HttpError as e:
        logger.error(
            f"Docs API error getting content: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        status_code = (
            e.resp.status
            if hasattr(e, "resp")
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Google Docs document with ID '{document_id}' not found.",
            )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to retrieve document content: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error getting document content: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving document content.",
        )


@router.post(
    "/{document_id}/write",
    response_model=Message,
    summary="Write content to a Google Docs document",
)
async def write_to_google_doc(
    document_id: str,
    request: WriteDocRequest,
    docs_service: GoogleDocsService = Depends(get_docs_service),
):
    """
    Writes text content to a Google Docs document.
    Can insert at a specific index, or append to the end.
    Optionally deletes all existing content before writing.
    """
    if document_id != request.document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mismatch between document_id in path and request body.",
        )

    try:
        await docs_service.write_to_document(
            document_id=document_id,
            text=request.text_content,
            index=request.insert_index,
            delete_existing=request.delete_existing_content,
        )
        return {
            "message": f"Content successfully written to Google Docs document '{document_id}'."
        }
    except HttpError as e:
        logger.error(
            f"Docs API error writing content: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        status_code = (
            e.resp.status
            if hasattr(e, "resp")
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        if status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Google Docs document with ID '{document_id}' not found.",
            )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to write content to document: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error writing content: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while writing content to document.",
        )
