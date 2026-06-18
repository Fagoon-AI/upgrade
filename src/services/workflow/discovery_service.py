import json
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from loguru import logger

from src.models.sql.workflow.document import KnowledgeDocument
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class DiscoveryConfig:
    """Configuration for discovery service."""
    default_limit: int = 5
    max_limit: int = 50
    min_similarity: float = 0.3
    keyword_boost: float = 0.2
    embedding_model: str = "models/text-embedding-004"
    cache_ttl_seconds: int = 300  # 5 minutes
    max_query_length: int = 10000
    min_query_length: int = 3


# Simple in-memory cache (use Redis in production)
_embedding_cache: Dict[str, Tuple[List[float], datetime]] = {}


# ============================================================
# DISCOVERY SERVICE
# ============================================================

class DiscoveryService:
    """
    Semantic Discovery Service.

    Features:
    - Semantic search using vector embeddings
    - Hybrid search (vector + keyword)
    - Result ranking and filtering
    - Query preprocessing
    - Embedding caching
    - Multi-tenancy isolation
    - Error handling with fallbacks

    Search Modes:
    - semantic: Pure vector similarity
    - hybrid: Vector + keyword boosting
    - keyword: Traditional keyword search (fallback)
    """

    def __init__(self, config: Optional[DiscoveryConfig] = None):
        self.config = config or DiscoveryConfig()

    # ============================================================
    # MAIN SEARCH METHODS
    # ============================================================

    @staticmethod
    async def semantic_search(
        db: AsyncSession,
        user_id: UUID,
        query: str,
        connection_id: UUID,
        limit: int = 5,
        min_similarity: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic search across user's documents.

        Args:
            db: Database session
            user_id: User ID for multi-tenancy
            query: Search query
            connection_id: AI connection for embeddings
            limit: Max results
            min_similarity: Minimum similarity threshold
            filters: Optional filters (e.g., filename, date_range)

        Returns:
            List of search results with scores
        """
        service = DiscoveryService()
        return await service._do_semantic_search(
            db, user_id, query, connection_id, limit, min_similarity, filters
        )

    async def _do_semantic_search(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        connection_id: UUID,
        limit: int = 5,
        min_similarity: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Internal semantic search implementation."""
        # Validate and preprocess query
        query = self._preprocess_query(query)
        if not query:
            return []

        # Apply limits
        limit = min(max(1, limit), self.config.max_limit)
        min_sim = min_similarity or self.config.min_similarity

        try:
            # Get embedding
            query_vector = await self._get_embedding(
                db=db,
                connection_id=connection_id,
                text=query,
                user_id=user_id
            )

            if not query_vector:
                logger.warning("Failed to get embedding, falling back to keyword search")
                return await self._keyword_search(db, user_id, query, limit)

            # Build and execute search query
            results = await self._vector_search(
                db=db,
                user_id=user_id,
                query_vector=query_vector,
                limit=limit,
                min_similarity=min_sim,
                filters=filters
            )

            return results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            # Fallback to keyword search
            return await self._keyword_search(db, user_id, query, limit)

    async def hybrid_search(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        connection_id: UUID,
        limit: int = 5,
        keyword_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Performs hybrid search combining vector and keyword matching.

        Args:
            db: Database session
            user_id: User ID
            query: Search query
            connection_id: AI connection for embeddings
            limit: Max results
            keyword_weight: Weight for keyword matching (0-1)

        Returns:
            List of search results with combined scores
        """
        query = self._preprocess_query(query)
        if not query:
            return []

        limit = min(max(1, limit), self.config.max_limit)

        try:
            # Get embedding
            query_vector = await self._get_embedding(
                db=db,
                connection_id=connection_id,
                text=query,
                user_id=user_id
            )

            if not query_vector:
                return await self._keyword_search(db, user_id, query, limit)

            # Hybrid query with keyword boost
            stmt = text("""
                SELECT 
                    content, 
                    filename, 
                    chunk_index,
                    created_at,
                    (
                        (1 - (embedding <=> :vector)) * :vector_weight +
                        CASE WHEN content ILIKE :query_pattern THEN :keyword_weight ELSE 0 END
                    ) as hybrid_score
                FROM knowledgedocument
                WHERE user_id = :user_id
                ORDER BY hybrid_score DESC
                LIMIT :limit
            """)

            result = await db.execute(stmt, {
                "vector": str(query_vector),
                "user_id": user_id,
                "query_pattern": f"%{query}%",
                "vector_weight": 1 - keyword_weight,
                "keyword_weight": keyword_weight,
                "limit": limit
            })

            return self._format_results(result.all())

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return await self._keyword_search(db, user_id, query, limit)

    # ============================================================
    # EMBEDDING METHODS
    # ============================================================

    async def _get_embedding(
        self,
        db: AsyncSession,
        connection_id: UUID,
        text: str,
        user_id: UUID
    ) -> Optional[List[float]]:
        """Gets embedding for text, with caching."""
        # Check cache
        cache_key = self._get_cache_key(text)
        cached = self._get_cached_embedding(cache_key)
        if cached:
            return cached

        try:
            # Get connection
            result = await db.execute(
                select(Connection).where(Connection.id == connection_id)
            )
            connection = result.scalars().first()

            if not connection:
                logger.error(f"Connection not found: {connection_id}")
                return None

            # Verify ownership
            if connection.user_id != user_id:
                logger.error(f"Connection ownership mismatch")
                return None

            # Decrypt credentials
            creds = json.loads(crypto.decrypt(connection.encrypted_credentials))
            api_key = creds.get("api_key")

            if not api_key:
                logger.error("No API key in connection")
                return None

            # Generate embedding
            from google import genai
            client = genai.Client(api_key=api_key)

            response = await asyncio.to_thread(
                client.models.embed_content,
                model=self.config.embedding_model,
                contents=text
            )

            if response.embeddings:
                vector = response.embeddings[0].values
                # Cache the result
                self._cache_embedding(cache_key, vector)
                return vector

            return None

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    def _get_cache_key(self, text: str) -> str:
        """Generates cache key for text."""
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def _get_cached_embedding(self, key: str) -> Optional[List[float]]:
        """Gets cached embedding if not expired."""
        if key in _embedding_cache:
            vector, timestamp = _embedding_cache[key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self.config.cache_ttl_seconds):
                return vector
            else:
                del _embedding_cache[key]
        return None

    def _cache_embedding(self, key: str, vector: List[float]) -> None:
        """Caches embedding."""
        # Simple cache cleanup
        if len(_embedding_cache) > 1000:
            # Remove oldest entries
            now = datetime.now(timezone.utc)
            expired_keys = [
                k for k, (_, ts) in _embedding_cache.items()
                if now - ts > timedelta(seconds=self.config.cache_ttl_seconds)
            ]
            for k in expired_keys:
                del _embedding_cache[k]

        _embedding_cache[key] = (vector, datetime.now(timezone.utc))

    # ============================================================
    # SEARCH IMPLEMENTATIONS
    # ============================================================

    async def _vector_search(
        self,
        db: AsyncSession,
        user_id: UUID,
        query_vector: List[float],
        limit: int,
        min_similarity: float,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Performs pure vector similarity search."""
        # Build query
        base_query = """
            SELECT 
                content, 
                filename, 
                chunk_index,
                created_at,
                1 - (embedding <=> :vector) as similarity
            FROM knowledgedocument
            WHERE user_id = :user_id
            AND 1 - (embedding <=> :vector) >= :min_similarity
        """

        params = {
            "vector": str(query_vector),
            "user_id": user_id,
            "min_similarity": min_similarity,
            "limit": limit
        }

        # Apply filters
        if filters:
            if filters.get("filename"):
                base_query += " AND filename = :filename"
                params["filename"] = filters["filename"]

            if filters.get("date_from"):
                base_query += " AND created_at >= :date_from"
                params["date_from"] = filters["date_from"]

            if filters.get("date_to"):
                base_query += " AND created_at <= :date_to"
                params["date_to"] = filters["date_to"]

        base_query += " ORDER BY similarity DESC LIMIT :limit"

        result = await db.execute(text(base_query), params)
        return self._format_results(result.all())

    async def _keyword_search(
        self,
        db: AsyncSession,
        user_id: UUID,
        query: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback keyword search."""
        stmt = text("""
            SELECT 
                content, 
                filename, 
                chunk_index,
                created_at,
                0.5 as similarity
            FROM knowledgedocument
            WHERE user_id = :user_id
            AND content ILIKE :query_pattern
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        result = await db.execute(stmt, {
            "user_id": user_id,
            "query_pattern": f"%{query}%",
            "limit": limit
        })

        return self._format_results(result.all())

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _preprocess_query(self, query: str) -> str:
        """Preprocesses search query."""
        if not query:
            return ""

        query = query.strip()

        # Length validation
        if len(query) < self.config.min_query_length:
            return ""

        if len(query) > self.config.max_query_length:
            query = query[:self.config.max_query_length]

        return query

    def _format_results(self, rows: List[Any]) -> List[Dict[str, Any]]:
        """Formats database results."""
        results = []

        for row in rows:
            content, filename, chunk_index, created_at, score = row

            results.append({
                "content": content,
                "source": filename,
                "chunk_index": chunk_index,
                "date": created_at.isoformat() if created_at else None,
                "relevance_score": round(float(score) * 100, 2)
            })

        return results

    # ============================================================
    # DOCUMENT MANAGEMENT
    # ============================================================

    async def get_document_stats(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Gets document statistics for a user."""
        stmt = text("""
            SELECT 
                COUNT(*) as total_chunks,
                COUNT(DISTINCT filename) as total_files,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM knowledgedocument
            WHERE user_id = :user_id
        """)

        result = await db.execute(stmt, {"user_id": user_id})
        row = result.first()

        if not row:
            return {
                "total_chunks": 0,
                "total_files": 0,
                "oldest": None,
                "newest": None
            }

        return {
            "total_chunks": row[0] or 0,
            "total_files": row[1] or 0,
            "oldest": row[2].isoformat() if row[2] else None,
            "newest": row[3].isoformat() if row[3] else None
        }

    async def list_documents(
        self,
        db: AsyncSession,
        user_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Lists all documents for a user."""
        stmt = text("""
            SELECT 
                filename,
                COUNT(*) as chunk_count,
                MIN(created_at) as created_at
            FROM knowledgedocument
            WHERE user_id = :user_id
            GROUP BY filename
            ORDER BY MIN(created_at) DESC
            LIMIT :limit
        """)

        result = await db.execute(stmt, {"user_id": user_id, "limit": limit})

        return [
            {
                "filename": row[0],
                "chunk_count": row[1],
                "created_at": row[2].isoformat() if row[2] else None
            }
            for row in result.all()
        ]

    async def delete_document(
        self,
        db: AsyncSession,
        user_id: UUID,
        filename: str
    ) -> int:
        """Deletes all chunks for a document."""
        stmt = text("""
            DELETE FROM knowledgedocument
            WHERE user_id = :user_id AND filename = :filename
        """)

        result = await db.execute(stmt, {"user_id": user_id, "filename": filename})
        await db.commit()

        return result.rowcount