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
from src.embeddings.openai_embeddings import OpenAIEmbedding
from src.schemas.document import Document
from src.schemas.enums import EmbeddingModelType

class IngestionManager:
    def __init__(self, vector_store: PgVectorStorage):
        self.vector_store = vector_store
        self.doc_processor = DocumentProcessor()
        self.embedding_service = OpenAIEmbedding(model_type=EmbeddingModelType.TEXT_EMBEDDING_3_SMALL)

    async def ingest_knowledge_base(self, agent_id: str, knowledge_base: KnowledgeBase):
        """Processes and ingests files from the knowledge base."""
        all_chunks = []
        collection_name = f"agent_{agent_id}"

        for file_ref in knowledge_base.uploaded_files or []:
            # file_ref is path in 'uploaded_files' list
            actual_path = file_ref
            if not os.path.exists(actual_path):
                # Try with 'outputs' prefix for local storage compatibility
                actual_path = os.path.join("outputs", file_ref)
                if not os.path.exists(actual_path):
                    logger.warning(f"Knowledge file not found: {file_ref} or outputs/{file_ref}")
                    continue

            chunks = await self.doc_processor.process_file(actual_path)
            for chunk in chunks:
                chunk['metadata'] = {
                    "agent_id": agent_id,
                    "file_path": file_ref
                }
                all_chunks.append(chunk)

        if not all_chunks:
            return

        # Embed and Add
        vector_documents = []
        for chunk in all_chunks:
            embedding = self.embedding_service.create_embedding(chunk['content'])
            vector_documents.append(Document(
                id=str(uuid.uuid4()),
                content=chunk['content'],
                embedding=embedding,
                metadata=chunk['metadata']
            ))

        await self.vector_store.add(vector_documents, collection_name)
        logger.success(f"Ingested {len(vector_documents)} chunks for agent {agent_id}.")
