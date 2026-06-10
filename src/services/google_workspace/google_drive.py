import io
from loguru import logger
from typing import Dict, List, Optional, Union
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload



class GoogleDriveService:
    def __init__(self, credentials: Credentials):
        """
        Initializes the Google Drive API service.
        Args:
            credentials: The google.oauth2.credentials.Credentials object.
        """
        self.credentials = credentials
        self._service = None

    @property
    def service(self):
        """
        Returns the Drive API service client, building it if it doesn't exist.
        """
        if self._service is None:
            try:
                self._service = build("drive", "v3", credentials=self.credentials)
                logger.info("Google Drive API service built successfully.")
            except Exception as e:
                logger.error(
                    "Error building Google Drive API service: {}", e, exc_info=True
                )
                raise HttpError(f"Could not build Drive service: {e}")
        return self._service

    async def list_files(
        self,
        query: Optional[
            str
        ] = None,
        page_size: int = 10,
        fields: Optional[
            str
        ] = "files(id, name, mimeType, modifiedTime, parents, size)",
        corpora: Optional[str] = "user",
    ) -> List[Dict]:
        """
        Lists files and folders in Google Drive.
        Args:
            query (str): A query string to filter results (Drive API search syntax).
            page_size (int): The maximum number of results to return per page.
            fields (str): Fields to return for each file (partial response).
            corpora (str): The source of the files (user, allDrives, domain, drive).
        Returns:
            List[Dict]: A list of file/folder metadata dictionaries.
        Raises:
            HttpError: If the Drive API call fails.
        """
        try:
            # Use 'q' for query, 'pageSize' for limit, 'fields' for partial response
            results = (
                self.service.files()
                .list(q=query, pageSize=page_size, fields=fields, corpora=corpora)
                .execute()
            )
            items = results.get("files", [])
            logger.info("Listed {} Drive items with query '{}'.", len(items), query)
            return items
        except HttpError as error:
            logger.error("Failed to list Drive files: {}", error, exc_info=True)
            raise

    async def create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Dict:
        """
        Creates a new folder in Google Drive.
        Args:
            folder_name (str): The name of the new folder.
            parent_id (str): The ID of the parent folder where this new folder will be created.
                             If None, creates in the root.
        Returns:
            Dict: Metadata of the created folder.
        Raises:
            HttpError: If the Drive API call fails.
        """
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]

        try:
            folder = self.service.files().create(
                body=file_metadata,
                fields="id, name, parents, mimeType"
            ).execute()
            logger.info("Created folder '{}' with ID: {}", folder_name, folder.get('id'))
            return folder
        except HttpError as error:
            logger.error("Failed to create folder '{}': {}", folder_name, error, exc_info=True)
            raise

    async def upload_file(
        self,
        file_name: str,
        file_content: bytes,
        mime_type: str,
        parent_id: Optional[str] = None,
        convert_to_google_format: bool = False
    ) -> Dict:
        """
        Uploads a file to Google Drive.
        Args:
            file_name (str): The name of the file to upload.
            file_content (bytes): The raw content of the file as bytes.
            mime_type (str): The MIME type of the file (e.g., 'text/plain', 'application/pdf').
            parent_id (str): The ID of the parent folder. If None, uploads to root.
            convert_to_google_format (bool): Whether to convert to a Google Workspace format.
        Returns:
            Dict: Metadata of the uploaded file.
        Raises:
            HttpError: If the Drive API call fails.
        """
        file_metadata = {
            "name": file_name,
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]

        if convert_to_google_format:
            if mime_type == "text/plain":
                file_metadata["mimeType"] = "application/vnd.google-apps.document"
            elif mime_type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/csv"]:
                file_metadata["mimeType"] = "application/vnd.google-apps.spreadsheet"
            logger.info("Attempting to convert '{}' from {} to Google format.", file_name, mime_type)
        else:
            file_metadata["mimeType"] = mime_type


        media_body = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=mime_type,
            resumable=True
        )

        try:
            uploaded_file = self.service.files().create(
                body=file_metadata,
                media_body=media_body,
                fields="id, name, mimeType, parents, webViewLink, webContentLink"
            ).execute()
            logger.info("Uploaded file '{}' with ID: {}", file_name, uploaded_file.get('id'))
            return uploaded_file
        except HttpError as error:
            logger.error("Failed to upload file '{}': {}", file_name, error, exc_info=True)
            raise

    async def delete_file(self, file_id: str) -> Dict:
        """
        Deletes a file or folder from Google Drive (moves to trash).
        Args:
            file_id (str): The ID of the file/folder to delete.
        Returns:
            Dict: An empty dictionary on success (as per Drive API v3 delete).
        Raises:
            HttpError: If the Drive API call fails.
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info("Deleted file/folder with ID: {}", file_id)
            return {
                "message": f"File/folder {file_id} successfully deleted (moved to trash)."
            }
        except HttpError as error:
            logger.error(
                "Failed to delete file/folder {}: {}", file_id, error, exc_info=True
            )
            raise


    async def download_file(self, file_id: str) -> bytes:
        """
        Downloads a file from Google Drive.
        Args:
            file_id (str): The ID of the file to download.
        Returns:
            bytes: The content of the file as bytes.
        Raises:
            HttpError: If the Drive API call fails.
            HTTPException 400: If the file type is not downloadable.
        """
        try:
            file_metadata = self.service.files().get(fileId=file_id, fields="name, mimeType").execute()
            mime_type = file_metadata.get('mimeType')
            file_name = file_metadata.get('name')

            request = None

            google_docs_editor_mime_types = {
                "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.google-apps.drawing": "image/png",
                "application/vnd.google-apps.script": "application/vnd.google-apps.script+json",
            }

            if mime_type in google_docs_editor_mime_types:
                export_mime_type = google_docs_editor_mime_types[mime_type]
                request = self.service.files().export_media(fileId=file_id, mimeType=export_mime_type)
                logger.info("Exporting Google Docs Editor file '{}' ({}) to {}.", file_name, mime_type, export_mime_type)
            elif mime_type == "application/vnd.google-apps.folder":
                # Folders cannot be downloaded
                logger.warning("Attempted to download a folder: '{}' ({}). Folders cannot be downloaded directly.", file_name, file_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot download folder '{file_name}'. Provide a file ID."
                )
            elif mime_type.startswith("application/vnd.google-apps"):
                # Handle other obscure Google Apps types that might not have a direct export
                logger.warning("Attempted to download unsupported Google Apps type: '{}' ({}). Not supported for direct export/download.", file_name, mime_type)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot download Google Apps file of type '{mime_type}'. It may not be exportable to a standard format."
                )
            else:
                # Regular files (PDF, image, etc.)
                request = self.service.files().get_media(fileId=file_id)
                logger.info("Downloading regular file '{}' ({}).", file_name, mime_type)

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to prepare file download request. Unknown file type or configuration error."
                )

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                logger.info("Download progress for file {}: {}%", file_id, int(status.progress() * 100))
            fh.seek(0)
            logger.info("Downloaded file content for ID: {}", file_id)
            return fh.getvalue()
        except HttpError as error:
            logger.error("Failed to download file {}: {}", file_id, error, exc_info=True)
            raise
        except HTTPException as e:
            raise
        except Exception as e:
            logger.error("Unexpected error during download of file {}: {}", file_id, e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during download: {e}"
            )
