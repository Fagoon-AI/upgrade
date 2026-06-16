import os
import uuid
from typing import List, Dict, Optional
from pathlib import Path
from fastapi import UploadFile, HTTPException
from loguru import logger
from src.storages.file_storage import FileStorageService
from src.services.nosql.postgres_services import PostgresServices

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".csv"}

def validate_file_extension(filename: str):
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed. Supported formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

class FileService:
    """
    Handles the business logic for processing and storing files.
    Interconnects agent uploads with the user's Knowledge Base.
    """
    def __init__(self, storage_service: FileStorageService):
        self.storage_service = storage_service
        logger.info("FileService initialized.")

    async def process_and_upload_files(
            self, user_id: str, agent_id: str, files: List[UploadFile], pg_services: Optional[PostgresServices] = None
    ) -> List[dict]:
        """
        Processes a list of uploaded files, validates extensions, uploads them to GCS, and
        records them in the PostgreSQL knowledge base database (file_references table).

        Args:
            user_id (str): The ID of the user.
            agent_id (str): The ID of the agent.
            files (List[UploadFile]): The list of files from the request.

        Returns:
            List[dict]: A list of dictionaries containing the original filename
                        and the remote GCS storage path for each uploaded file.
        """
        uploaded_files_metadata = []
        for file in files:
            try:
                # Validate file extension
                validate_file_extension(file.filename)

                # Read file content into memory
                file_bytes = await file.read()

                # Define a structured, predictable destination path in GCS
                destination_path = f"{user_id}/agents/{agent_id}/sources/{file.filename}"

                logger.info(f"Uploading '{file.filename}' to GCS destination: {destination_path}")

                # Use the storage service to upload the file bytes directly to GCS
                gcs_path = self.storage_service.upload_file_to_agent_folder(
                    file_bytes=file_bytes,
                    destination_path=destination_path,
                    content_type=file.content_type
                )

                uploaded_files_metadata.append({
                    "file_name": file.filename,
                    "gcs_path": gcs_path, 
                })
                logger.success(f"Successfully uploaded to GCS and recorded path for '{file.filename}'.")

            except HTTPException as he:
                logger.warning(f"File validation failed for '{file.filename}': {he.detail}")
                uploaded_files_metadata.append({
                    "file_name": file.filename,
                    "gcs_path": None,
                    "error": he.detail
                })
            except Exception as e:
                logger.error("Failed to process and upload file '{}': {}", file.filename, e, exc_info=True)
                uploaded_files_metadata.append({
                    "file_name": file.filename,
                    "gcs_path": None,
                    "error": f"Failed to upload file to GCS: {e}"
                })
            finally:
                # Ensure file stream is closed
                await file.close()

        return uploaded_files_metadata

    async def save_file_to_bucket(
        self, user_id: str, conversation_id: str, files: List[UploadFile]
    ) -> List[Dict[str, str]]:
        """Save uploaded files into Storage (compatibility method for upgrade chat router)"""
        uploaded_files = []

        for file in files:
            try:
                validate_file_extension(file.filename)
                file_bytes = await file.read()
                content_type = file.content_type or "application/octet-stream"

                destination_path = f"{user_id}/{conversation_id}/{file.filename}"
                uploaded_path = self.storage_service.upload_file_to_upgrade_folder(
                    file_bytes=file_bytes,
                    destination_path=destination_path,
                    content_type=content_type
                )

                uploaded_files.append({
                    "filename": file.filename,
                    "file_path": uploaded_path,
                })
            except Exception as e:
                logger.error(f"Failed to save file '{file.filename}' to storage: {e}")
                raise HTTPException(status_code=500, detail=f"Upload failed for {file.filename}: {e}")
            finally:
                await file.close()

        return uploaded_files
