import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.models.sql.models import DocumentChunk, FileReference
from src.storages.vectordb_storages.base import (
    VectorDBQuery,
    VectorDBQueryResult,
    VectorDBStatus,
)
from src.schemas.document import Document
from src.core.database.postgres import PostgresManager

class PgVectorStorage:
    def __init__(self, postgres_manager: PostgresManager, vector_dim: int = 1536):
        self.postgres_manager = postgres_manager
        self.vector_dim = vector_dim
        logger.info("PgVectorStorage initialized.")

    async def ensure_collection_exists(self, collection_name: str) -> None:
        """
        In Postgres, we don't necessarily need 'collections' as separate tables.
        We can use the collection_name as a metadata filter.
        """
        # For now, this is a no-op as the table is created by migrations/SQL setup
        pass

    async def add(self, records: List[Document], collection_name: str, **kwargs) -> None:
        """Adds vectors to the document_chunks table."""
        async with self.postgres_manager.get_session() as session:
            try:
                for record in records:
                    # We might need to find or create a FileReference first if not present
                    # but for RAG ingestion, file_id is often in metadata
                    file_id = record.metadata.get("file_id") or record.metadata.get("document_id")
                    
                    # Find file_ref_id
                    stmt = select(FileReference.id).where(FileReference.file_id == file_id)
                    result = await session.execute(stmt)
                    file_ref_id = result.scalar_one_or_none()
                    
                    if not file_ref_id:
                        # Create a dummy or partial FileReference if it doesn't exist
                        # In a real migration, this should be handled by the ingestion service
                        new_file_ref = FileReference(
                            file_id=file_id or f"unknown_{uuid.uuid4()}",
                            user_id=record.metadata.get("user_id") or uuid.UUID(int=0), # Placeholder
                            metadata=record.metadata
                        )
                        session.add(new_file_ref)
                        await session.flush()
                        file_ref_id = new_file_ref.id

                    chunk = DocumentChunk(
                        id=uuid.UUID(record.id) if isinstance(record.id, str) and len(record.id) == 36 else uuid.uuid4(),
                        file_ref_id=file_ref_id,
                        content=record.content,
                        embedding=record.embedding,
                        metadata={**record.metadata, "collection": collection_name}
                    )
                    session.add(chunk)
                
                await session.commit()
                logger.success(f"Successfully added {len(records)} vectors to Postgres (PgVector).")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to add vectors to PgVector: {e}", exc_info=True)
                raise RuntimeError(f"Failed to add vectors to PgVector: {e}")

    async def query(
        self,
        query: VectorDBQuery,
        collection_name: str,
        filter_conditions: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[VectorDBQueryResult]:
        """Searches for similar vectors using cosine distance (<=>)."""
        async with self.postgres_manager.get_session() as session:
            try:
                # Construct query with pgvector operator
                # SELECT *, embedding <=> :query_embedding as distance 
                # FROM document_chunks 
                # WHERE metadata->>'collection' = :collection
                # ORDER BY distance ASC LIMIT :top_k
                
                stmt = select(
                    DocumentChunk,
                    DocumentChunk.embedding.cosine_distance(query.query_vector).label("distance")
                ).where(
                    text("metadata->>'collection' = :col").bindparams(col=collection_name)
                )

                if filter_conditions:
                    for key, value in filter_conditions.items():
                        stmt = stmt.where(text(f"metadata->>'{key}' = :val").bindparams(val=str(value)))

                stmt = stmt.order_by(text("distance ASC")).limit(query.top_k)
                
                result = await session.execute(stmt)
                rows = result.all()
                
                query_results = []
                for chunk, distance in rows:
                    query_results.append(
                        VectorDBQueryResult.create(
                            id=str(chunk.id),
                            similarity=1 - distance, # distance is cosine distance, similarity is 1 - distance
                            payload={**chunk.metadata, "content": chunk.content},
                            vector=list(chunk.embedding)
                        )
                    )
                return query_results
            except Exception as e:
                logger.error(f"Failed to query PgVector: {e}", exc_info=True)
                raise RuntimeError(f"Failed to query PgVector: {e}")

    async def status(self) -> VectorDBStatus:
        async with self.postgres_manager.get_session() as session:
            stmt = select(func.count(DocumentChunk.id))
            result = await session.execute(stmt)
            count = result.scalar()
            return VectorDBStatus(vector_dim=self.vector_dim, vector_count=count)
