import asyncio
from loguru import logger
from typing import List, Dict, Any
import os
import uuid
from pydantic import BaseModel, Field

from src.schemas.agents import KnowledgeBase
from src.storages.file_storage import FileStorageService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.services.document_processor import DocumentProcessor
from src.schemas.document import Document
from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService

class IngestionManager:
    def __init__(self, vector_store: PgVectorStorage):
        self.vector_store = vector_store
        self.doc_processor = DocumentProcessor()
        self.file_storage = FileStorageService()

    async def ingest_knowledge_base(self, agent_id: str, knowledge_base: KnowledgeBase):
        """Processes and ingests files from the knowledge base."""
        all_chunks = []
        collection_name = f"agent_{agent_id}"

        from src.models.sql.models import FileReference
        from sqlalchemy import select

        for file_ref in knowledge_base.uploaded_files or []:
            try:
                # Check if the file exists physically in the storage
                file_exists = False
                try:
                    if hasattr(self.file_storage.manager, 'base_dir'):
                        full_path = os.path.join(self.file_storage.manager.base_dir, file_ref)
                        if os.path.exists(full_path):
                            file_exists = True
                except Exception:
                    pass

                # If the file does not exist, check if we already have a FileReference for this file_ref.
                # If we do, we can skip processing because it was directly ingested.
                if not file_exists:
                    async with self.vector_store.postgres_manager.get_session() as session:
                        stmt = select(FileReference.id).where(FileReference.file_id == file_ref)
                        result = await session.execute(stmt)
                        file_ref_id = result.scalar_one_or_none()
                        if file_ref_id:
                            logger.info(f"File '{file_ref}' has already been directly ingested. Cloning chunks for agent {agent_id}.")
                            from src.models.sql.models import DocumentChunk
                            chunk_stmt = select(DocumentChunk).where(DocumentChunk.file_ref_id == file_ref_id)
                            existing_chunks = await session.execute(chunk_stmt)
                            new_chunks = []
                            for chunk in existing_chunks.scalars():
                                new_meta = dict(chunk.extra_metadata)
                                new_meta["agent_id"] = agent_id
                                new_meta["collection"] = collection_name
                                new_chunks.append(DocumentChunk(
                                    id=uuid.uuid4(),
                                    file_ref_id=file_ref_id,
                                    content=chunk.content,
                                    embedding=chunk.embedding,
                                    extra_metadata=new_meta
                                ))
                            if new_chunks:
                                session.add_all(new_chunks)
                                await session.commit()
                                logger.success(f"Cloned {len(new_chunks)} existing chunks for agent {agent_id}.")
                            continue

                # 1. Download file bytes from Google Cloud Storage into memory
                file_bytes = self.file_storage.read_file(file_ref)
                
                # 2. Process the file using DocumentProcessor
                processed_doc = await self.doc_processor.process_single_file(filename=os.path.basename(file_ref), file_bytes=file_bytes)
                
                if processed_doc.status == "error":
                    logger.error(f"Failed to extract text from {file_ref}: {processed_doc.error}")
                    continue
                    
                # 3. Collect chunks
                for page_data in processed_doc.data or []:
                    metadata = page_data.metadata.copy() if page_data.metadata else {}
                    metadata.update({
                        "agent_id": agent_id,
                        "file_name": os.path.basename(file_ref)
                    })
                    all_chunks.append({
                        "content": page_data.content,
                        "metadata": metadata
                    })
            except Exception as e:
                logger.error(f"Error processing file {file_ref} for RAG: {e}", exc_info=True)

        if not all_chunks:
            return

        # 4. Resolve API Key and Setup LLM Service for Embeddings
        # We need the user_id for the resolver. Since we don't have user_id directly here,
        # we can extract it from the agent model via PostgresManager.
        try:
            from src.services.nosql.postgres_services import PostgresServices
            async with self.vector_store.postgres_manager.get_session() as session:
                pg_services = PostgresServices(session)
                agent = await pg_services.get_agent_by_id(uuid.UUID(agent_id))
                user_id = str(agent.user_id) if agent else None

            if not user_id:
                raise ValueError("Could not find user_id for the given agent_id to resolve embedding service.")

            from src.services.embeddings import get_embedding_service
            embedding_service = await get_embedding_service(user_id=user_id, agent_id=agent_id)

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

            await self.vector_store.add(vector_documents, collection_name)
            logger.success(f"Ingested {len(vector_documents)} chunks for agent {agent_id}.")
        except Exception as e:
            logger.error(f"Failed to embed and save chunks for agent {agent_id}: {e}", exc_info=True)
