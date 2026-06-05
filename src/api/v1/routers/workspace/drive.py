import base64
from typing import List, Optional
from loguru import logger
from fastapi import (APIRouter, Depends, File, HTTPException, Query,
                     UploadFile, status)
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from .deps import get_google_credentials
from src.schemas.workspace.common import Message
from src.schemas.workspace.drive import (CreateFolderRequest, DeleteFileRequest,
                               DriveFile, FileContentResponse,
                               UploadFileRequest)
from src.services.google_workspace.google_drive import GoogleDriveService


router = APIRouter()

async def get_drive_service(
    credentials: Credentials = Depends(get_google_credentials),
) -> GoogleDriveService:
    return GoogleDriveService(credentials)


@router.get(
    "/files",
    response_model=List[DriveFile],
    summary="List Google Drive files and folders",
)
async def list_drive_files(
    query: Optional[str] = Query(
        None,
        description="Google Drive search query (e.g., 'mimeType=\"image/jpeg\"' or 'name contains \"report\"')",
    ),
    page_size: int = Query(
        10, ge=1, le=100, description="Maximum number of files/folders to retrieve"
    ),
    drive_service: GoogleDriveService = Depends(get_drive_service),
):
    """
    Lists files and folders from Google Drive based on a search query.
    """
    try:
        files = await drive_service.list_files(query=query, page_size=page_size)
        return [DriveFile(**f) for f in files]
    except HttpError as e:
        logger.error(
            f"Drive API error listing files: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to list Drive files: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error listing Drive files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while listing Drive files.",
        )


@router.post(
    "/folders",
    response_model=DriveFile,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new folder in Google Drive",
)
async def create_drive_folder(
    request: CreateFolderRequest,
    drive_service: GoogleDriveService = Depends(get_drive_service),
):
    """
    Creates a new folder in Google Drive.
    """
    try:
        folder = await drive_service.create_folder(
            folder_name=request.folder_name, parent_id=request.parent_id
        )
        return DriveFile(**folder)
    except HttpError as e:
        logger.error(
            f"Drive API error creating folder: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to create folder: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error creating folder: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating folder.",
        )


@router.post(
    "/upload",
    response_model=DriveFile,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to Google Drive",
)
async def upload_drive_file(
    file_name: str = Query(..., description="The name for the file."),
    mime_type: str = Query(
        ..., description="The MIME type of the file (e.g., 'text/plain', 'image/png')."
    ),
    parent_id: Optional[str] = Query(
        None, description="The ID of the parent folder. If omitted, uploads to root."
    ),
    convert_to_google_format: bool = Query(
        False,
        description="If true, attempts to convert the uploaded file to a Google Workspace format (e.g., .docx to Google Docs).",
    ),
    file: UploadFile = File(..., description="The file content to upload."),
    drive_service: GoogleDriveService = Depends(get_drive_service),
):
    """
    Uploads a file to Google Drive.
    The file content is sent as a `multipart/form-data` part.
    """
    try:
        file_content = await file.read()
        uploaded_file = await drive_service.upload_file(
            file_name=file_name,
            file_content=file_content,
            mime_type=mime_type,
            parent_id=parent_id,
            convert_to_google_format=convert_to_google_format,
        )
        return DriveFile(**uploaded_file)
    except HttpError as e:
        logger.error(
            f"Drive API error uploading file: {e.content.decode() if e.content else e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=(
                e.resp.status
                if hasattr(e, "resp")
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=f"Failed to upload file: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error uploading file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while uploading file.",
        )


@router.get(
    "/download/{file_id}",
    response_model=FileContentResponse,
    summary="Download a file from Google Drive",
)
async def download_drive_file(
    file_id: str, drive_service: GoogleDriveService = Depends(get_drive_service)
):
    """
    Downloads the content of a file from Google Drive.
    For Google Workspace native formats (Docs, Sheets), it exports to a common format.
    The content is returned as base64 encoded string.
    """
    try:
        file_content_bytes = await drive_service.download_file(file_id)

        file_metadata = (
            drive_service.service.files()
            .get(fileId=file_id, fields="name, mimeType")
            .execute()
        )

        return FileContentResponse(
            file_id=file_id,
            file_name=file_metadata.get("name"),
            mime_type=file_metadata.get("mimeType"),
            content_base64=base64.b64encode(file_content_bytes).decode("utf-8"),
        )
    except HttpError as e:
        logger.error(
            f"Drive API error downloading file: {e.content.decode() if e.content else e}",
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
                detail=f"File with ID '{file_id}' not found or no content available.",
            )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to download file: {e.content.decode() if e.content else e}",
        )
    except Exception as e:
        logger.error(f"Unexpected error downloading file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while downloading file.",
        )
