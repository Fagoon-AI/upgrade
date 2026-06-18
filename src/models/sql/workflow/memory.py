import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime, String, Integer, Index, Text, text, Boolean
from pydantic import field_validator


# ============================================================
# CONFIGURATION
# ============================================================

# Valid roles for memory entries
VALID_ROLES = {"user", "assistant", "system", "tool", "function"}

# Content limits
MAX_CONTENT_LENGTH = 100000  # 100KB per entry
MAX_CONVERSATION_ID_LENGTH = 255

# Token estimation (rough: 4 chars per token)
CHARS_PER_TOKEN = 4


# ============================================================
# WORKFLOW MEMORY MODEL
# ============================================================

class WorkflowMemory(SQLModel, table=True):
    """
    Long-term memory store for workflow conversations.

    Features:
    - UUID primary key
    - Workflow association
    - Conversation threading
    - Role-based messages
    - Metadata storage
    - Token estimation
    - TTL support

    Use Cases:
    - Chat history storage
    - Agent context
    - State persistence
    - Audit trail

    Indexes:
    - Primary key on id
    - Index on workflow_id
    - Index on conversation_id
    - Composite index for queries
    """

    __tablename__ = "workflowmemory"

    # Primary key
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique memory entry identifier"
    )

    # Associations
    workflow_id: uuid.UUID = Field(
        index=True,
        description="Parent workflow ID"
    )

    conversation_id: str = Field(
        sa_column=Column(String(MAX_CONVERSATION_ID_LENGTH), nullable=False, index=True),
        description="Conversation thread identifier"
    )

    # Message data
    role: str = Field(
        sa_column=Column(String(20), nullable=False),
        description="Message role (user, assistant, system, tool)"
    )

    content: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Message content"
    )

    # Metadata
    metadata_json: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="JSON metadata (tool calls, citations, etc.)"
    )

    # Token estimation
    token_count: Optional[int] = Field(
        default=None,
        description="Estimated token count"
    )

    # Sequence tracking
    sequence_number: Optional[int] = Field(
        default=None,
        description="Order within conversation"
    )

    # Status flags
    is_pinned: bool = Field(
        default=False,
        sa_column=Column(Boolean, default=False),
        description="Pinned messages are always included"
    )

    is_summarized: bool = Field(
        default=False,
        sa_column=Column(Boolean, default=False),
        description="Message has been summarized"
    )

    # TTL support
    expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Auto-expire timestamp"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
        description="Creation timestamp"
    )

    # Table configuration
    __table_args__ = (
        # Composite index for conversation queries
        Index("ix_memory_workflow_conversation", "workflow_id", "conversation_id"),

        # Index for chronological retrieval
        Index("ix_memory_conversation_created", "conversation_id", "created_at"),

        # Index for sequence ordering
        Index("ix_memory_conversation_sequence", "conversation_id", "sequence_number"),

        # Index for TTL cleanup
        Index("ix_memory_expires", "expires_at"),
    )

    # ============================================================
    # VALIDATORS
    # ============================================================

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validates role value."""
        if not v:
            raise ValueError("Role is required")

        v = v.lower().strip()

        if v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

        return v

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validates content."""
        if v is None:
            return ""

        v = str(v)

        if len(v) > MAX_CONTENT_LENGTH:
            raise ValueError(f"Content exceeds maximum length ({MAX_CONTENT_LENGTH})")

        return v

    @field_validator("conversation_id", mode="before")
    @classmethod
    def validate_conversation_id(cls, v: str) -> str:
        """Validates conversation ID."""
        if not v:
            raise ValueError("Conversation ID is required")

        v = str(v).strip()

        if len(v) > MAX_CONVERSATION_ID_LENGTH:
            v = v[:MAX_CONVERSATION_ID_LENGTH]

        return v

    # ============================================================
    # PROPERTIES
    # ============================================================

    @property
    def is_expired(self) -> bool:
        """Checks if memory entry has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def estimated_tokens(self) -> int:
        """Estimates token count."""
        if self.token_count:
            return self.token_count
        return len(self.content) // CHARS_PER_TOKEN

    @property
    def content_preview(self) -> str:
        """Gets content preview (first 100 chars)."""
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."

    # ============================================================
    # METHODS
    # ============================================================

    def compute_token_count(self) -> int:
        """Computes and stores estimated token count."""
        self.token_count = len(self.content) // CHARS_PER_TOKEN
        return self.token_count

    def set_ttl(self, hours: int = 24) -> None:
        """Sets expiration time."""
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    def get_metadata(self) -> Dict[str, Any]:
        """Parses and returns metadata."""
        if not self.metadata_json:
            return {}

        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Sets metadata as JSON."""
        self.metadata_json = json.dumps(metadata)

    def update_metadata(self, updates: Dict[str, Any]) -> None:
        """Updates metadata with new values."""
        current = self.get_metadata()
        current.update(updates)
        self.set_metadata(current)

    def to_message_dict(self) -> Dict[str, str]:
        """Converts to LLM message format."""
        return {
            "role": self.role,
            "content": self.content
        }

    def to_dict(self, include_metadata: bool = True) -> Dict[str, Any]:
        """
        Converts to dictionary.

        Args:
            include_metadata: Include parsed metadata

        Returns:
            Dictionary representation
        """
        data = {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "token_count": self.estimated_tokens,
            "sequence_number": self.sequence_number,
            "is_pinned": self.is_pinned,
            "is_summarized": self.is_summarized,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if include_metadata:
            data["metadata"] = self.get_metadata()

        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
            data["is_expired"] = self.is_expired

        return data

    def to_history_line(self) -> str:
        """Converts to history format string."""
        return f"{self.role}: {self.content}"

    def __repr__(self) -> str:
        return f"<WorkflowMemory {self.role}[{self.conversation_id}]>"


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def format_conversation_history(
        memories: List[WorkflowMemory],
        max_tokens: Optional[int] = None,
        include_system: bool = True
) -> str:
    """
    Formats memories as conversation history string.

    Args:
        memories: List of memory entries
        max_tokens: Maximum tokens to include
        include_system: Include system messages

    Returns:
        Formatted conversation string
    """
    lines = []
    total_tokens = 0

    # Sort by sequence or created_at
    sorted_memories = sorted(
        memories,
        key=lambda m: (m.sequence_number or 0, m.created_at)
    )

    for memory in sorted_memories:
        # Skip expired
        if memory.is_expired:
            continue

        # Skip system if not included
        if not include_system and memory.role == "system":
            continue

        # Check token limit
        if max_tokens:
            if total_tokens + memory.estimated_tokens > max_tokens:
                break
            total_tokens += memory.estimated_tokens

        lines.append(memory.to_history_line())

    return "\n".join(lines)


def build_message_list(
        memories: List[WorkflowMemory],
        max_messages: Optional[int] = None
) -> List[Dict[str, str]]:
    """
    Builds LLM message list from memories.

    Args:
        memories: List of memory entries
        max_messages: Maximum messages to include

    Returns:
        List of message dictionaries
    """
    # Sort by sequence or created_at
    sorted_memories = sorted(
        memories,
        key=lambda m: (m.sequence_number or 0, m.created_at)
    )

    # Filter expired and convert
    messages = [
        m.to_message_dict()
        for m in sorted_memories
        if not m.is_expired
    ]

    # Limit if needed
    if max_messages and len(messages) > max_messages:
        # Keep system messages and last N messages
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        remaining = max_messages - len(system_msgs)
        messages = system_msgs + other_msgs[-remaining:]

    return messages