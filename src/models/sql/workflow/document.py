import uuid
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime, String, Integer, Index, Text, text
from pgvector.sqlalchemy import Vector
from pydantic import field_validator


# ============================================================
# CONFIGURATION
# ============================================================

EMBEDDING_DIMENSIONS = 768  # Gemini embedding-004
MAX_CONTENT_LENGTH = 50000  # 50KB per chunk
MAX_FILENAME_LENGTH = 500


# ============================================================
# KNOWLEDGE DOCUMENT MODEL
# ============================================================

class KnowledgeDocument(SQLModel, table=True):
    """
    Stores text chunks and their vector embeddings for RAG.

    Features:
    - UUID primary key
    - User isolation (multi-tenancy)
    - Vector embedding storage
    - Chunk metadata
    - Source tracking
    - Content validation

    Indexes:
    - Primary key on id
    - Index on user_id for multi-tenancy
    - Index on filename for grouping
    - Vector index for similarity search (HNSW)

    Vector Search:
        Uses pgvector with cosine distance (<=>)
        HNSW index for fast approximate nearest neighbor
    """

    __tablename__ = "knowledgedocument"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique document chunk identifier"
    )

    # Multi-tenancy
    user_id: uuid.UUID = Field(
        index=True,
        description="Owner user ID for data isolation"
    )

    # Source metadata
    filename: str = Field(
        sa_column=Column(String(MAX_FILENAME_LENGTH), nullable=False, index=True),
        description="Source document filename"
    )

    # Chunk metadata
    chunk_index: int = Field(
        sa_column=Column(Integer, nullable=False, default=0),
        description="Index of this chunk within the source document"
    )

    total_chunks: Optional[int] = Field(
        default=None,
        description="Total chunks in the source document"
    )

    # Content
    content: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Text content of this chunk"
    )

    content_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(64)),
        description="SHA-256 hash for deduplication"
    )

    # Vector embedding
    embedding: List[float] = Field(
        sa_column=Column(Vector(EMBEDDING_DIMENSIONS)),
        description=f"Vector embedding ({EMBEDDING_DIMENSIONS} dimensions)"
    )

    # Additional metadata
    metadata_json: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="JSON metadata (page number, section, etc.)"
    )

    # Processing info
    embedding_model: Optional[str] = Field(
        default="text-embedding-004",
        sa_column=Column(String(100)),
        description="Model used for embedding"
    )

    char_count: Optional[int] = Field(
        default=None,
        description="Character count of content"
    )

    word_count: Optional[int] = Field(
        default=None,
        description="Word count of content"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Ingestion timestamp"
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last update timestamp"
    )

    # Table configuration with indexes
    __table_args__ = (
        # Composite index for user queries
        Index("ix_knowledge_user_filename", "user_id", "filename"),

        # Index for chunk ordering
        Index("ix_knowledge_filename_chunk", "filename", "chunk_index"),

        # Content hash index for deduplication
        Index("ix_knowledge_content_hash", "content_hash"),
    )

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validates and cleans content."""
        if not v:
            raise ValueError("Content cannot be empty")

        v = v.strip()

        if len(v) > MAX_CONTENT_LENGTH:
            raise ValueError(f"Content exceeds maximum length ({MAX_CONTENT_LENGTH})")

        return v

    @field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validates and sanitizes filename."""
        if not v:
            raise ValueError("Filename is required")

        v = v.strip()

        # Remove potentially dangerous characters
        v = re.sub(r'[<>:"|?*\\]', '_', v)

        if len(v) > MAX_FILENAME_LENGTH:
            v = v[:MAX_FILENAME_LENGTH]

        return v

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_first_chunk(self) -> bool:
        """Checks if this is the first chunk."""
        return self.chunk_index == 0

    @property
    def is_last_chunk(self) -> bool:
        """Checks if this is the last chunk."""
        if self.total_chunks is None:
            return False
        return self.chunk_index == self.total_chunks - 1

    @property
    def content_preview(self) -> str:
        """Gets content preview (first 200 chars)."""
        if len(self.content) <= 200:
            return self.content
        return self.content[:200] + "..."

    # ============================================================
    # METHODS
    # ============================================================

    def compute_content_hash(self) -> str:
        """Computes SHA-256 hash of content."""
        import hashlib
        return hashlib.sha256(self.content.encode()).hexdigest()

    def compute_stats(self) -> None:
        """Computes content statistics."""
        self.char_count = len(self.content)
        self.word_count = len(self.content.split())

    def get_metadata(self) -> Dict[str, Any]:
        """Parses and returns metadata."""
        if not self.metadata_json:
            return {}

        try:
            import json
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Sets metadata as JSON."""
        import json
        self.metadata_json = json.dumps(metadata)

    def to_dict(self, include_embedding: bool = False) -> Dict[str, Any]:
        """
        Converts to dictionary.

        Args:
            include_embedding: Include the vector (large)

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "filename": self.filename,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "content": self.content,
            "content_preview": self.content_preview,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "embedding_model": self.embedding_model,
            "metadata": self.get_metadata(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if include_embedding and self.embedding:
            data["embedding"] = self.embedding

        return data

    def to_search_result(self, score: float = 0.0) -> Dict[str, Any]:
        """
        Converts to search result format.

        Args:
            score: Similarity score

        Returns:
            Search result dictionary
        """
        return {
            "content": self.content,
            "source": self.filename,
            "chunk_index": self.chunk_index,
            "date": self.created_at.isoformat() if self.created_at else None,
            "relevance_score": round(score * 100, 2),
            "metadata": self.get_metadata()
        }

    def __repr__(self) -> str:
        return f"<KnowledgeDocument {self.filename}[{self.chunk_index}]>"