# from typing import List, Dict
# from fastapi import UploadFile
# from loguru import logger
# from pathlib import Path
#
# from src.utils.common import async_time_execution
# from src.services.document_processor import DocumentProcessor
# from src.storages.file_storage import FileStorageService
#
#
# class FileService:
#     def __init__(
#         self,
#         file_storage_service: FileStorageService,
#         document_processor: DocumentProcessor,
#     ):
#         self.file_storage_service = file_storage_service
#         self.document_processor = document_processor
#
#     async def upload_single_file(
#         self, user_id: str, agent_id: str, file: UploadFile
#     ) -> Dict:
#         logger.debug(f"Processing file: {file.filename}")
#         file_bytes = await file.read()
#         destination_path = f"{user_id}/{agent_id}/{file.filename}"
#
#         self.file_storage_service.upload_file_to_agent_folder(
#             file_bytes=file_bytes,
#             destination_path=destination_path,
#             content_type=file.content_type,
#         )
#
#         return {
#             "filename": file.filename,
#             "path": destination_path,
#         }
#
#     @async_time_execution
#     async def process_and_upload_files(
#         self, user_id: str, agent_id: str, files: List[UploadFile]
#     ) -> List[Dict]:
#         logger.debug(f"Received total: {len(files)} files")
#         uploaded_files = []
#
#         for file in files:
#             file_info = await self.upload_single_file(user_id, agent_id, file)
#             uploaded_files.append(file_info)
#
#         return uploaded_files
#
#     async def save_file_to_bucket(
#         self, user_id: str, conversation_id: str, files: List[UploadFile]
#     ) -> List[Dict[str, str]]:
#         """Save uploaded files into Google Storage"""
#         uploaded_files = []
#
#         for file in files:
#             file_bytes = await file.read()
#             content_type = file.content_type or "application/octet-stream"
#
#             # TODO: Extract the document content from the file, and save data into google cloud
#             processed_document = await self.document_processor.process_single_file(filename=file.filename, file_bytes=file_bytes)
#
#             destination_path = f"{user_id}/{conversation_id}/{Path(file.filename).stem}.json"
#             json_path = self.file_storage_service.write_json_file(
#                 data=processed_document.model_dump(),
#                 file_path=destination_path,
#                 file_prefix="upgrade",
#             )
#             logger.debug(f"Data content extracted successfully and written to path: {json_path}")
#
#             destination_path = f"{user_id}/{conversation_id}/{file.filename}"
#             uploaded_path = self.file_storage_service.upload_file_to_upgrade_folder(file_bytes=file_bytes,
#                                                                     destination_path=destination_path,
#                                                                     content_type=content_type)
#
#             uploaded_files.append(
#                 {
#                     "filename": file.filename,
#                     "file_path": uploaded_path,
#                     "extracted_content_path": json_path
#                 }
#             )
#
#         return uploaded_files



from typing import List
from fastapi import UploadFile
from loguru import logger
from src.storages.file_storage import FileStorageService

class FileService:
    """
    Handles the business logic for processing and storing files.
    """
    def __init__(self, storage_service: FileStorageService):
        self.storage_service = storage_service
        logger.info("FileService initialized.")

    async def process_and_upload_files(
            self, user_id: str, agent_id: str, files: List[UploadFile]
    ) -> List[dict]:
        """
        Processes a list of uploaded files and uploads them to a structured
        path in the configured file storage (e.g., GCS).

        Args:
            user_id (str): The ID of the user.
            agent_id (str): The ID of the agent.
            files (List[UploadFile]): The list of files from the request.

        Returns:
            List[dict]: A list of dictionaries containing the original filename
                        and the final storage path for each uploaded file.
        """
        uploaded_files_metadata = []
        for file in files:
            try:
                # Read file content into memory
                file_bytes = await file.read()

                # Define a structured, predictable destination path
                # This path will be stored in the agent's knowledge base
                destination_path = f"{user_id}/agents/{agent_id}/sources/{file.filename}"

                logger.info(f"Uploading '{file.filename}' to destination: {destination_path}")

                # Use the storage service to upload the file bytes
                gcs_path = self.storage_service.upload_file_to_agent_folder(
                    file_bytes=file_bytes,
                    destination_path=destination_path,
                    content_type=file.content_type
                )

                uploaded_files_metadata.append({
                    "file_name": file.filename,
                    "gcs_path": gcs_path
                })
                logger.success(f"Successfully uploaded and recorded path for '{file.filename}'.")

            except Exception as e:
                logger.error("Failed to process and upload file '{}': {}", file.filename, e, exc_info=True)
                # Decide if one failure should stop the whole batch or just be skipped
                raise RuntimeError(f"Could not upload {file.filename}.") from e
            finally:
                # Ensure file stream is closed
                await file.close()

        return uploaded_files_metadata
