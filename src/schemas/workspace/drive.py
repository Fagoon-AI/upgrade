from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, HttpUrl


class DriveFile(BaseModel):
    id: str = Field(..., description="The unique ID of the Drive file or folder.")
    name: str = Field(..., description="The name of the file or folder.")
    mime_type: str = Field(
        ...,
        alias="mimeType",
        description="The MIME type of the file (e.g., 'text/plain', 'application/vnd.google-apps.folder').",
    )
    modified_time: Optional[str] = Field(
        None,
        alias="modifiedTime",
        description="The last time the file was modified (ISO 8601 timestamp).",
    )
    parents: Optional[List[str]] = Field(
        None, description="The IDs of the parent folders. Empty for root files."
    )
    size: Optional[int] = Field(
        None, description="The size of the file in bytes (only for files, not folders)."
    )
    web_view_link: Optional[HttpUrl] = Field(
        None,
        alias="webViewLink",
        description="A link to the file that the user can open in a browser.",
    )
    web_content_link: Optional[HttpUrl] = Field(
        None,
        alias="webContentLink",
        description="A link to download the file directly.",
    )

    class Config:
        validate_by_name = True


class CreateFolderRequest(BaseModel):
    folder_name: str = Field(
        ..., min_length=1, max_length=255, description="The name for the new folder."
    )
    parent_id: Optional[str] = Field(
        None,
        description="The ID of the parent folder to create this folder in. If omitted, created in root.",
    )


class UploadFileRequest(BaseModel):
    file_name: str = Field(
        ..., min_length=1, description="The name for the file to upload."
    )
    mime_type: str = Field(
        ...,
        description="The MIME type of the file (e.g., 'text/plain', 'image/png', 'application/pdf').",
    )
    parent_id: Optional[str] = Field(
        None,
        description="The ID of the parent folder to upload this file into. If omitted, uploaded to root.",
    )
    convert_to_google_format: bool = Field(
        False,
        description="If true, attempts to convert the uploaded file to a Google Workspace format (e.g., .docx to Google Docs).",
    )


class FileContentResponse(BaseModel):
    file_id: str
    file_name: str
    mime_type: str
    content_base64: str = Field(..., description="Base64 encoded content of the file.")
    # Use base64 encoding for safe transfer of binary data in JSON


class DeleteFileRequest(BaseModel):
    file_id: str = Field(
        ..., description="The ID of the file or folder to delete (moves to trash)."
    )
