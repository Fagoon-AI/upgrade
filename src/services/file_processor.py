import base64
import fitz  # PyMuPDF
import uuid
from typing import Any, Dict, List
from loguru import logger
from pydantic import BaseModel

from src.storages.file_storage import FileStorageService
from src.services.nosql.postgres_services import PostgresServices
from src.core.database.postgres import PostgresManager

class FileProcessingResult(BaseModel):
    """A simple data class to hold the results of file processing."""
    content: List[Dict[str, Any]] = []
    errors: List[str] = []


class FileProcessor:
    """
    Handles processing of uploaded files (e.g., from GCS) for inclusion
    in the LLM context using PostgreSQL for metadata.
    """
    def __init__(self, storage_service: FileStorageService, postgres_manager: PostgresManager):
        self._storage_service = storage_service
        self._postgres_manager = postgres_manager

    async def process_files_for_llm(self, file_ids: List[str]) -> FileProcessingResult:
        """
        Fetches files by their IDs from PostgreSQL, processes them based on MIME type,
        and returns their content structured for a multi-modal LLM prompt.
        """
        llm_content_blocks = []
        processing_errors = []

        if not file_ids:
            return FileProcessingResult()

        async with self._postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            file_references = await pg_services.get_file_references_by_ids(file_ids)

        if len(file_references) != len(file_ids):
            logger.warning(f"Mismatch between requested file_ids ({len(file_ids)}) and found DB references.")

        for ref in file_references:
            # ref is FileReference model instance
            filename = ref.extra_metadata.get('filename', 'Unknown file')
            try:
                file_bytes = self._storage_service.read_file(ref.extra_metadata['gcs_path'])
                mime_type = ref.extra_metadata.get('mime_type', '')

                if mime_type.startswith('image/'):
                    base64_content = base64.b64encode(file_bytes).decode('utf-8')
                    llm_content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{base64_content}"}
                    })
                elif 'pdf' in mime_type:
                    doc_text = ""
                    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                        for page in doc:
                            doc_text += page.get_text()
                    llm_content_blocks.append({
                        "type": "text",
                        "text": f"--- Start of content from {filename} ---\n\n{doc_text}\n\n--- End of content from {filename} ---",
                    })
                else:
                    logger.warning(f"Unhandled MIME type for LLM context: {mime_type}. Skipping file {filename}.")

            except Exception as e:
                logger.error(f"Failed to process file ID {ref.file_id} ({filename}): {e}", exc_info=True)
                processing_errors.append(f"Failed to process file: {filename}")

        return FileProcessingResult(content=llm_content_blocks, errors=processing_errors)
