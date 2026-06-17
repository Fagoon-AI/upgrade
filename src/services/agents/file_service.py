import os
import uuid
from typing import List, Dict, Optional
from pathlib import Path
from fastapi import UploadFile, HTTPException
from loguru import logger
from src.storages.file_storage import FileStorageService
from src.services.nosql.postgres_services import PostgresServices
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.services.document_processor import DocumentProcessor
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.schemas.document import Document
from src.services.api_key_resolver import resolve_api_key

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
            self,
            user_id: str,
            agent_id: str,
            files: List[UploadFile],
            pg_services: Optional[PostgresServices] = None,
            vector_store: Optional[PgVectorStorage] = None
    ) -> List[dict]:
        """
        Processes a list of uploaded files, validates extensions, extracts pages,
        generates embeddings, and stores them directly in PgVector without uploading to GCS/local.

        Args:
            user_id (str): The ID of the user.
            agent_id (str): The ID of the agent.
            files (List[UploadFile]): The list of files from the request.
            pg_services (Optional[PostgresServices]): Services for Postgres.
            vector_store (Optional[PgVectorStorage]): PgVector Storage.

        Returns:
            List[dict]: A list of dictionaries containing the original filename
                        and the remote GCS storage path for each uploaded file.
        """
        uploaded_files_metadata = []

        if vector_store:
            try:
                api_key = await resolve_api_key(
                    user_id=uuid.UUID(user_id),
                    provider="gemini",
                    feature="agents",
                    specific_id=agent_id
                )
            except Exception as e:
                logger.error(f"Failed to resolve API key: {e}")
                api_key = None

            llm_config = BaseLLMConfig(
                provider="gemini",
                model="gemini-embedding-2",
                api_key=api_key
            )
            embedding_service = LLMService(config=llm_config)
            doc_processor = DocumentProcessor()

        for file in files:
            try:
                # Validate file extension
                validate_file_extension(file.filename)

                # Read file content into memory
                file_bytes = await file.read()

                if vector_store:
                    # Direct chunking, embedding and storing in PgVector
                    processed_doc = await doc_processor.process_single_file(
                        filename=file.filename,
                        file_bytes=file_bytes
                    )

                    if processed_doc.status == "error":
                        raise HTTPException(status_code=500, detail=f"Failed to extract text: {processed_doc.error}")

                    all_chunks = []
                    file_id = f"{user_id}/agents/{agent_id}/sources/{file.filename}"
                    for page_data in processed_doc.data or []:
                        metadata = page_data.metadata.copy() if page_data.metadata else {}
                        metadata.update({
                            "agent_id": agent_id,
                            "file_name": file.filename,
                            "file_id": file_id,
                            "user_id": user_id,
                        })
                        all_chunks.append({
                            "content": page_data.content,
                            "metadata": metadata
                        })

                    # Embed and Add
                    vector_documents = []
                    for chunk in all_chunks:
                        if not chunk['content'].strip():
                            continue

                        embedding = await embedding_service.get_embeddings(chunk['content'])
                        vector_documents.append(Document(
                            id=str(uuid.uuid4()),
                            content=chunk['content'],
                            embedding=embedding,
                            metadata=chunk['metadata']
                        ))

                    collection_name = f"agent_{agent_id}"
                    await vector_store.add(vector_documents, collection_name)
                    logger.success(f"Directly ingested {len(vector_documents)} chunks for agent {agent_id} from '{file.filename}'.")

                    uploaded_files_metadata.append({
                        "file_name": file.filename,
                        "gcs_path": file_id,
                    })

                else:
                    # Fallback to standard upload if vector_store is not provided
                    destination_path = f"{user_id}/agents/{agent_id}/sources/{file.filename}"
                    logger.info(f"Fallback: Uploading '{file.filename}' to GCS destination: {destination_path}")

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
                logger.error("Failed to process and ingest file '{}': {}", file.filename, e, exc_info=True)
                uploaded_files_metadata.append({
                    "file_name": file.filename,
                    "gcs_path": None,
                    "error": f"Failed to ingest file: {e}"
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
