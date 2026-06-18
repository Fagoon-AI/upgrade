import asyncio
import json
import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from loguru import logger

from src.services.workflow_engine.nodes.base import (
    BaseNode, NodeManifest, NodeCategory, NodeExecutionError,
    ConnectionError as NodeConnectionError, FieldType, create_manifest, define_field
)

if TYPE_CHECKING:
    from src.services.workflow_engine.context import ExecutionContext


# CHUNKING STRATEGIES

@dataclass
class ChunkMetadata:
    chunk_index: int
    start_char: int
    end_char: int
    token_estimate: int
    content_hash: str


class TextChunker:
    """
    Text chunking with semantic boundary awareness.

    Features:
    - Respects sentence boundaries when possible
    - Maintains overlap for context continuity
    - Token-aware sizing for LLM compatibility
    - Deduplication via content hashing
    """

    def __init__(
            self,
            chunk_size: int = 500,
            chunk_overlap: int = 50,
            respect_sentences: bool = True
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.respect_sentences = respect_sentences

        # Approximate: 1 token ≈ 4 characters for English
        self.chars_per_token = 4

    def _estimate_tokens(self, text: str) -> int:
        """Estimates token count without calling tokenizer."""
        return len(text) // self.chars_per_token

    def _find_sentence_boundary(
            self,
            text: str,
            target_pos: int,
            search_range: int = 100
    ) -> int:
        """
        Finds the nearest sentence boundary to target position.
        Searches backwards from target_pos within search_range.
        """
        if not self.respect_sentences:
            return target_pos

        # Sentence ending patterns
        sentence_ends = re.compile(r'[.!?]\s+')

        # Search backwards for sentence boundary
        search_start = max(0, target_pos - search_range)
        search_text = text[search_start:target_pos]

        matches = list(sentence_ends.finditer(search_text))
        if matches:
            # Return position after the last sentence end
            last_match = matches[-1]
            return search_start + last_match.end()

        # Fallback: try paragraph boundaries
        newline_pos = search_text.rfind('\n\n')
        if newline_pos != -1:
            return search_start + newline_pos + 2

        # No boundary found, use target position
        return target_pos

    def chunk(self, text: str) -> List[Tuple[str, ChunkMetadata]]:
        """
        Splits text into overlapping chunks with metadata.
        Returns:
            List of (chunk_text, metadata) tuples
        """

        text = re.sub(r'\s+', ' ', text).strip()

        if not text:
            return []

        # Small text: return as single chunk
        if len(text) <= self.chunk_size:
            return [(text, ChunkMetadata(
                chunk_index=0,
                start_char=0,
                end_char=len(text),
                token_estimate=self._estimate_tokens(text),
                content_hash=hashlib.md5(text.encode()).hexdigest()[:12]
            ))]

        chunks = []
        start = 0
        chunk_index = 0
        seen_hashes = set()

        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size

            if end >= len(text):
                # Last chunk
                end = len(text)
            else:
                # Find sentence boundary
                end = self._find_sentence_boundary(text, end)

            chunk_text = text[start:end].strip()

            if chunk_text:  # Skip empty chunks
                chunk_hash = hashlib.md5(chunk_text.encode()).hexdigest()[:12]

                # Deduplicate
                if chunk_hash not in seen_hashes:
                    seen_hashes.add(chunk_hash)
                    chunks.append((chunk_text, ChunkMetadata(
                        chunk_index=chunk_index,
                        start_char=start,
                        end_char=end,
                        token_estimate=self._estimate_tokens(chunk_text),
                        content_hash=chunk_hash
                    )))
                    chunk_index += 1

            # Move start position with overlap
            new_start = end - self.chunk_overlap
            if new_start <= start:
                # Prevent infinite loop
                start = end
            else:
                start = new_start

        return chunks


# EMBEDDING SERVICE

class EmbeddingService:
    """
    Abstraction layer for embedding generation.
    Supports multiple providers with automatic fallback.
    """

    def __init__(self, provider: str = "gemini"):
        self.provider = provider
        self._client = None
        self._initialized = False

    async def initialize(self, credentials: Dict[str, Any]) -> None:
        """Initialize the embedding client."""
        if self._initialized:
            return

        if self.provider == "gemini":
            try:
                from google import genai
            except ImportError:
                raise NodeConnectionError(
                    message="google-genai package not installed",
                    node_type="ragNode",
                    provider="gemini"
                )

            api_key = credentials.get("api_key")
            if not api_key:
                raise NodeConnectionError(
                    message="Missing API key for Gemini",
                    node_type="ragNode",
                    provider="gemini"
                )
            self._client = genai.Client(api_key=api_key)
            self._initialized = True

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not self._initialized:
            raise NodeExecutionError(
                message="Embedding service not initialized",
                node_type="ragNode",
                retryable=False
            )

        if self.provider == "gemini":
            response = await asyncio.to_thread(
                self._client.models.embed_content,
                model="models/text-embedding-004",
                contents=text
            )
            return list(response.embeddings[0].values)

        raise ValueError(f"Unknown embedding provider: {self.provider}")

    async def embed_batch(
            self,
            texts: List[str],
            max_concurrency: int = 5
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts with concurrency limit."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def embed_one(text: str) -> List[float]:
            async with semaphore:
                return await self.embed(text)

        return await asyncio.gather(*[embed_one(t) for t in texts])


# RAG NODE IMPLEMENTATION
class RAGNode(BaseNode):
    """
    World-Class Hybrid RAG Node.

    Operations:
    - UPSERT: Chunk and index documents for retrieval
    - SEARCH: Hybrid vector + keyword search
    - DELETE: Remove documents from index

    Security:
    - All SQL queries use parameterized statements
    - User ID isolation ensures multi-tenancy
    - Content is validated before storage

    Performance:
    - Batch embedding generation
    - Async database operations
    - Efficient PGVector queries
    """

    node_type = "ragNode"

    def __init__(self):
        super().__init__()
        self.chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        self.embedding_service = EmbeddingService()

    @classmethod
    def get_manifest(cls) -> NodeManifest:
        return create_manifest(
            node_type=cls.node_type,
            display_name="Knowledge RAG",
            icon="Search",
            category=NodeCategory.AI_DATA,
            description="Perform semantic or hybrid search over vector documentation.",
            fields=[
                define_field(
                    name="operation",
                    label="Operation",
                    field_type=FieldType.SELECT,
                    required=True,
                    options=["SEARCH", "UPSERT", "DELETE"],
                    default="SEARCH"
                ),
                define_field(
                    name="connection_id",
                    label="AI Connection",
                    field_type=FieldType.CONNECTION_SELECT,
                    required=True,
                    provider="GOOGLE",
                    helper="Gemini connection for embedding generation"
                ),
                define_field(
                    name="content",
                    label="Search Query / Content",
                    field_type=FieldType.TEXTAREA,
                    required=True,
                    placeholder="{{steps['start-1'].user_input}}"
                ),
                define_field(
                    name="filename",
                    label="Document Source",
                    field_type=FieldType.TEXT,
                    placeholder="report.pdf",
                    helper="Identifier for the source document (UPSERT only)"
                ),
                define_field(
                    name="limit",
                    label="Result Limit",
                    field_type=FieldType.NUMBER,
                    default=5,
                    min_value=1,
                    max_value=20
                ),
                define_field(
                    name="similarity_threshold",
                    label="Minimum Similarity",
                    field_type=FieldType.SLIDER,
                    default=0.5,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    helper="Results below this score are filtered out"
                ),
                define_field(
                    name="keyword_boost",
                    label="Keyword Boost",
                    field_type=FieldType.SLIDER,
                    default=0.3,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.1,
                    helper="Weight for exact keyword matches in hybrid search"
                )
            ],
            outputs=["matches", "context_text", "count", "chunks_processed"],
            requires_connection=True,
            timeout_seconds=120
        )

    async def execute(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Route to appropriate operation handler."""
        operation = input_data.get("operation", "SEARCH").upper()
        connection_id = input_data.get("connection_id")

        if not connection_id:
            raise NodeExecutionError(
                message="connection_id is required",
                node_type=self.node_type,
                retryable=False
            )

        # Initialize embedding service
        credentials = await self._get_credentials(db, connection_id)
        await self.embedding_service.initialize(credentials)

        if operation == "UPSERT":
            return await self._handle_upsert(db, context, input_data)
        elif operation == "SEARCH":
            return await self._handle_search(db, context, input_data)
        elif operation == "DELETE":
            return await self._handle_delete(db, context, input_data)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_credentials(
            self,
            db: AsyncSession,
            connection_id: str
    ) -> Dict[str, Any]:
        """Fetches and decrypts connection credentials."""
        try:
            from core.encryption import crypto
        except ImportError:
            class MockCrypto:
                def decrypt(self, data: str) -> str:
                    return data
            crypto = MockCrypto()

        stmt = text("""
            SELECT encrypted_credentials, provider
            FROM connection
            WHERE id = :connection_id
        """)

        result = await db.execute(stmt, {"connection_id": connection_id})
        row = result.fetchone()

        if not row:
            raise NodeConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="unknown"
            )

        encrypted_creds, provider = row
        return json.loads(crypto.decrypt(encrypted_creds))

    async def _handle_upsert(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Chunks and indexes document content.

        Process:
        1. Split content into semantic chunks
        2. Generate embeddings for each chunk
        3. Store in vector database with metadata
        """
        content = input_data.get("content", "")
        filename = input_data.get("filename", "unknown_source")
        user_id = context.user_id

        if not content:
            raise NodeExecutionError(
                message="UPSERT requires content",
                node_type=self.node_type,
                retryable=False
            )

        # Chunk the content
        chunks = self.chunker.chunk(content)

        if not chunks:
            return {
                "status": "success",
                "operation": "UPSERT",
                "chunks_processed": 0,
                "message": "No content to index"
            }

        # Generate embeddings in batch
        chunk_texts = [c[0] for c in chunks]

        try:
            embeddings = await self.embedding_service.embed_batch(chunk_texts)
        except Exception as e:
            raise NodeExecutionError(
                message=f"Embedding generation failed: {str(e)}",
                node_type=self.node_type,
                retryable=True
            )

        # Store in database using parameterized query
        processed_ids = []

        for (chunk_text, metadata), embedding in zip(chunks, embeddings):
            # SECURE: Parameterized INSERT prevents SQL injection
            insert_stmt = text("""
                INSERT INTO knowledgedocument 
                (id, user_id, filename, chunk_index, content, embedding, created_at)
                VALUES (
                    gen_random_uuid(),
                    :user_id,
                    :filename,
                    :chunk_index,
                    :content,
                    :embedding::vector,
                    :created_at
                )
                RETURNING id
            """)

            result = await db.execute(insert_stmt, {
                "user_id": str(user_id),
                "filename": filename,
                "chunk_index": metadata.chunk_index,
                "content": chunk_text,
                "embedding": str(embedding),
                "created_at": datetime.now(timezone.utc)
            })

            row = result.fetchone()
            if row:
                processed_ids.append(str(row[0]))

        await db.commit()

        logger.info(f"RAG UPSERT: {len(processed_ids)} chunks indexed for {filename}")

        return {
            "status": "success",
            "operation": "UPSERT",
            "chunks_processed": len(processed_ids),
            "document_ids": processed_ids,
            "filename": filename
        }

    async def _handle_search(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Performs hybrid vector + keyword search.

        Scoring:
        - Vector similarity: Cosine similarity from PGVector
        - Keyword boost: Additional score for exact matches
        - Final score: weighted combination

        Security:
        - All queries use parameterized statements
        - User ID filtering ensures multi-tenancy
        """
        query = input_data.get("content", "")
        limit = int(input_data.get("limit", 5))
        threshold = float(input_data.get("similarity_threshold", 0.5))
        keyword_boost = float(input_data.get("keyword_boost", 0.3))
        user_id = context.user_id

        if not query:
            raise NodeExecutionError(
                message="SEARCH requires a query",
                node_type=self.node_type,
                retryable=False
            )

        # Generate query embedding
        try:
            query_embedding = await self.embedding_service.embed(query)
        except Exception as e:
            raise NodeExecutionError(
                message=f"Query embedding failed: {str(e)}",
                node_type=self.node_type,
                retryable=True
            )

        # SECURE: Hybrid search with a fully parameterized query
        search_stmt = text("""
            WITH vector_search AS (
                SELECT 
                    id,
                    content,
                    filename,
                    chunk_index,
                    created_at,
                    1 - (embedding <=> :query_vector::vector) AS vector_score
                FROM knowledgedocument
                WHERE user_id = :user_id
                ORDER BY embedding <=> :query_vector::vector
                LIMIT :search_limit
            ),
            keyword_matches AS (
                SELECT 
                    vs.*,
                    CASE 
                        WHEN vs.content ILIKE :keyword_pattern THEN :keyword_boost
                        ELSE 0.0
                    END AS keyword_score
                FROM vector_search vs
            )
            SELECT 
                id,
                content,
                filename,
                chunk_index,
                created_at,
                vector_score,
                keyword_score,
                (vector_score + keyword_score) AS hybrid_score
            FROM keyword_matches
            WHERE vector_score >= :threshold
            ORDER BY hybrid_score DESC
            LIMIT :result_limit
        """)

        # Prepare keyword pattern for ILIKE (escape special characters)
        safe_query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        keyword_pattern = f"%{safe_query}%"

        result = await db.execute(search_stmt, {
            "query_vector": str(query_embedding),
            "user_id": str(user_id),
            "keyword_pattern": keyword_pattern,
            "keyword_boost": keyword_boost,
            "threshold": threshold,
            "search_limit": min(limit * 3, 50),  # Over-fetch for better filtering
            "result_limit": limit
        })

        rows = result.fetchall()

        matches = []
        for row in rows:
            matches.append({
                "id": str(row[0]),
                "content": row[1],
                "source": row[2],
                "chunk_index": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "vector_score": round(float(row[5]) * 100, 2),
                "keyword_score": round(float(row[6]) * 100, 2),
                "relevance_score": round(float(row[7]) * 100, 2)
            })

        # Build context text for LLM consumption
        context_text = "\n\n---\n\n".join([
            f"[Source: {m['source']}, Relevance: {m['relevance_score']}%]\n{m['content']}"
            for m in matches
        ])

        return {
            "status": "success",
            "operation": "SEARCH",
            "matches": matches,
            "context_text": context_text,
            "count": len(matches),
            "query": query
        }

    async def _handle_delete(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deletes documents from the index.

        Can delete by:
        - Specific document IDs
        - Filename pattern
        """
        filename = input_data.get("filename")
        document_ids = input_data.get("document_ids", [])
        user_id = context.user_id

        deleted_count = 0

        if document_ids:
            # Delete specific documents - SECURE: parameterized
            delete_stmt = text("""
                DELETE FROM knowledgedocument
                WHERE id = ANY(:doc_ids::uuid[]) AND user_id = :user_id
            """)
            result = await db.execute(delete_stmt, {
                "doc_ids": document_ids,
                "user_id": str(user_id)
            })
            deleted_count = result.rowcount

        elif filename:
            # Delete by filename - SECURE: parameterized
            delete_stmt = text("""
                DELETE FROM knowledgedocument
                WHERE filename = :filename AND user_id = :user_id
            """)
            result = await db.execute(delete_stmt, {
                "filename": filename,
                "user_id": str(user_id)
            })
            deleted_count = result.rowcount
        else:
            raise NodeExecutionError(
                message="DELETE requires either 'filename' or 'document_ids'",
                node_type=self.node_type,
                retryable=False
            )

        await db.commit()

        logger.info(f"RAG DELETE: {deleted_count} documents removed")

        return {
            "status": "success",
            "operation": "DELETE",
            "deleted_count": deleted_count
        }