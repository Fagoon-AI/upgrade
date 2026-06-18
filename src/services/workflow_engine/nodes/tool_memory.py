import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func, delete, select as sa_select
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.memory import WorkflowMemory


# ============================================================
# MEMORY MANAGEMENT CONFIGURATION
# ============================================================

class MemoryConfig:
    """Configuration for memory management."""

    # Default limits
    DEFAULT_MAX_MEMORIES_PER_CONVERSATION = 1000
    DEFAULT_MAX_TOTAL_TOKENS = 100_000  # ~400KB of text
    DEFAULT_RETENTION_DAYS = 30

    # Token estimation (Gemini averages ~4 chars per token)
    CHARS_PER_TOKEN = 4

    # Pruning strategies
    PRUNE_OLDEST = "oldest"       # Remove oldest memories first
    PRUNE_SUMMARIZE = "summarize" # Summarize old memories (requires AI)
    PRUNE_SLIDING = "sliding"     # Keep sliding window of recent memories


class TokenEstimator:
    """Estimates token counts for memory content."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimates tokens from text using character count."""
        if not text:
            return 0
        return len(text) // MemoryConfig.CHARS_PER_TOKEN

    @staticmethod
    def estimate_memory_tokens(memories: List[Dict[str, Any]]) -> int:
        """Estimates total tokens for a list of memories."""
        total = 0
        for mem in memories:
            content = mem.get("content", "")
            role = mem.get("role", "")
            # Add overhead for formatting: "role: content\n"
            total += TokenEstimator.estimate_tokens(f"{role}: {content}\n")
        return total


# ============================================================
# MEMORY NODE IMPLEMENTATION
# ============================================================

class MemoryNode(BaseNode):
    """
    Neural Memory Node.

    Features:
    - Automatic pruning to prevent unbounded growth
    - Token-aware history retrieval
    - Configurable retention policies
    - Efficient batch operations
    - Memory statistics and monitoring

    Operations:
    - add_memory: Store new memory with auto-pruning
    - get_all_memories: Retrieve with token limits
    - get_memory: Fetch specific memory
    - delete_memory: Remove specific or all memories
    - prune_memories: Manual cleanup trigger
    - get_stats: Memory usage statistics
    """

    node_type = "memoryNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Neural Memory",
            "icon": "BrainCircuit",
            "category": "Intelligence Tools",
            "description": "Manage long-term conversation state with automatic pruning.",
            "fields": [
                {
                    "name": "operation",
                    "label": "Memory Operation",
                    "type": "select",
                    "options": [
                        "add memory",
                        "get all memories",
                        "get memory",
                        "delete memory",
                        "prune memories",
                        "get stats"
                    ],
                    "default": "add memory"
                },
                {
                    "name": "conversation_id",
                    "label": "Conversation ID",
                    "type": "text",
                    "placeholder": "{{steps['start-1'].session_id}}",
                    "helper": "Defaults to Execution ID if empty."
                },
                {
                    "name": "role",
                    "label": "Role",
                    "type": "select",
                    "options": ["user", "assistant", "system", "tool"],
                    "default": "user",
                    "conditional": {"operation": ["add memory"]}
                },
                {
                    "name": "content",
                    "label": "Content to Persist",
                    "type": "textarea",
                    "conditional": {"operation": ["add memory"]}
                },
                {
                    "name": "limit",
                    "label": "Retrieval Limit",
                    "type": "number",
                    "default": 50,
                    "helper": "Max memories to retrieve",
                    "conditional": {"operation": ["get all memories"]}
                },
                {
                    "name": "max_tokens",
                    "label": "Max Tokens",
                    "type": "number",
                    "default": 50000,
                    "helper": "Token limit for retrieved history",
                    "conditional": {"operation": ["get all memories"]}
                },
                {
                    "name": "memory_id",
                    "label": "Memory ID",
                    "type": "text",
                    "conditional": {"operation": ["get memory", "delete memory"]}
                },
                {
                    "name": "max_memories",
                    "label": "Max Memories per Conversation",
                    "type": "number",
                    "default": 1000,
                    "helper": "Auto-prune when exceeded",
                    "conditional": {"operation": ["add memory"]}
                },
                {
                    "name": "retention_days",
                    "label": "Retention Days",
                    "type": "number",
                    "default": 30,
                    "helper": "Delete memories older than this",
                    "conditional": {"operation": ["prune memories"]}
                }
            ],
            "outputs": ["history_text", "memory_id", "count", "token_count", "status"]
        }

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Routes to appropriate operation handler."""
        operation = input_data.get("operation", "add memory").lower().strip()
        conversation_id = input_data.get("conversation_id") or context.execution_id
        workflow_id = context.workflow_id

        try:
            if operation == "add memory":
                return await self._add_memory(
                    db, workflow_id, conversation_id, input_data
                )
            elif operation == "get all memories":
                return await self._get_history(
                    db, workflow_id, conversation_id, input_data
                )
            elif operation == "get memory":
                return await self._get_single_memory(
                    db, input_data.get("memory_id")
                )
            elif operation == "delete memory":
                return await self._delete_memory(
                    db, workflow_id, conversation_id, input_data.get("memory_id")
                )
            elif operation == "prune memories":
                return await self._prune_memories(
                    db, workflow_id, conversation_id, input_data
                )
            elif operation == "get stats":
                return await self._get_stats(
                    db, workflow_id, conversation_id
                )
            else:
                raise NodeExecutionError(
                    message=f"Unknown operation: {operation}",
                    node_type=self.node_type,
                    retryable=False
                )

        except NodeExecutionError:
            raise
        except Exception as e:
            logger.error(f"Memory node error: {e}")
            raise NodeExecutionError(
                message=str(e),
                node_type=self.node_type,
                retryable=True
            )

    async def _add_memory(
            self,
            db: AsyncSession,
            workflow_id: str,
            conversation_id: str,
            data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Persists new memory with automatic pruning.

        Auto-prunes oldest memories when limit is exceeded.
        """
        role = data.get("role", "user")
        content = data.get("content")
        max_memories = int(data.get("max_memories", MemoryConfig.DEFAULT_MAX_MEMORIES_PER_CONVERSATION))

        if not content:
            raise NodeExecutionError(
                message="Memory 'add memory' requires 'content'",
                node_type=self.node_type,
                retryable=False
            )

        # 1. Check current count
        count_query = text("""
            SELECT COUNT(*) FROM workflowmemory
            WHERE workflow_id = :workflow_id
            AND conversation_id = :conversation_id
        """)

        result = await db.execute(count_query, {
            "workflow_id": workflow_id,
            "conversation_id": conversation_id
        })
        current_count = result.scalar() or 0

        # 2. Auto-prune if needed (delete oldest to make room)
        pruned_count = 0
        if current_count >= max_memories:
            # Calculate how many to delete (keep 90% of max)
            to_delete = current_count - int(max_memories * 0.9) + 1

            prune_query = text("""
                DELETE FROM workflowmemory
                WHERE id IN (
                    SELECT id FROM workflowmemory
                    WHERE workflow_id = :workflow_id
                    AND conversation_id = :conversation_id
                    ORDER BY created_at ASC
                    LIMIT :to_delete
                )
            """)

            delete_result = await db.execute(prune_query, {
                "workflow_id": workflow_id,
                "conversation_id": conversation_id,
                "to_delete": to_delete
            })
            pruned_count = delete_result.rowcount
            logger.info(f"Auto-pruned {pruned_count} old memories for conversation {conversation_id}")

        # 3. Add new memory
        new_memory = WorkflowMemory(
            workflow_id=workflow_id,
            conversation_id=conversation_id,
            role=role,
            content=str(content)
        )
        db.add(new_memory)
        await db.commit()
        await db.refresh(new_memory)

        # 4. Calculate token count
        token_count = TokenEstimator.estimate_tokens(f"{role}: {content}")

        return {
            "status": "success",
            "operation": "add memory",
            "memory_id": str(new_memory.id),
            "role": role,
            "token_count": token_count,
            "pruned_count": pruned_count
        }

    async def _get_history(
            self,
            db: AsyncSession,
            workflow_id: str,
            conversation_id: str,
            data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Retrieves conversation history with token-aware limits.

        Returns most recent memories that fit within token budget.
        """
        limit = int(data.get("limit", 50))
        max_tokens = int(data.get("max_tokens", 50000))

        # Query memories in chronological order
        query = (
            select(WorkflowMemory)
            .where(WorkflowMemory.workflow_id == workflow_id)
            .where(WorkflowMemory.conversation_id == conversation_id)
            .order_by(WorkflowMemory.created_at.desc())  # Most recent first
            .limit(limit)
        )

        result = await db.execute(query)
        memories = result.scalars().all()

        # Reverse to get chronological order
        memories = list(reversed(memories))

        # Apply token limit
        selected_memories = []
        total_tokens = 0

        for mem in memories:
            mem_text = f"{mem.role}: {mem.content}\n"
            mem_tokens = TokenEstimator.estimate_tokens(mem_text)

            if total_tokens + mem_tokens > max_tokens:
                # Would exceed limit, stop adding
                break

            selected_memories.append(mem)
            total_tokens += mem_tokens

        # Format as LLM-ready history string
        formatted_history = "\n".join([
            f"{m.role}: {m.content}" for m in selected_memories
        ])

        # Convert to dicts for JSON serialization
        memories_dict = []
        for m in selected_memories:
            try:
                memories_dict.append({
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None
                })
            except Exception:
                memories_dict.append({
                    "role": m.role,
                    "content": m.content
                })

        return {
            "status": "success",
            "operation": "get all memories",
            "history_text": formatted_history,
            "count": len(selected_memories),
            "total_available": len(memories),
            "token_count": total_tokens,
            "max_tokens": max_tokens,
            "truncated": len(selected_memories) < len(memories),
            "memories": memories_dict
        }

    async def _get_single_memory(
            self,
            db: AsyncSession,
            memory_id: str
    ) -> Dict[str, Any]:
        """Fetches a specific memory by ID."""
        if not memory_id:
            raise NodeExecutionError(
                message="'get memory' requires 'memory_id'",
                node_type=self.node_type,
                retryable=False
            )

        try:
            result = await db.get(WorkflowMemory, memory_id)
        except Exception:
            result = None

        if not result:
            return {
                "status": "error",
                "operation": "get memory",
                "error": "Memory not found"
            }

        return {
            "status": "success",
            "operation": "get memory",
            "memory": {
                "id": str(result.id),
                "role": result.role,
                "content": result.content,
                "created_at": result.created_at.isoformat() if result.created_at else None
            }
        }

    async def _delete_memory(
            self,
            db: AsyncSession,
            workflow_id: str,
            conversation_id: str,
            memory_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Deletes specific memory or entire conversation history.
        """
        deleted_count = 0

        if memory_id:
            # Delete specific memory
            delete_query = text("""
                DELETE FROM workflowmemory
                WHERE id = :memory_id
                AND workflow_id = :workflow_id
            """)
            result = await db.execute(delete_query, {
                "memory_id": memory_id,
                "workflow_id": workflow_id
            })
            deleted_count = result.rowcount
        else:
            # Delete all memories for conversation
            delete_query = text("""
                DELETE FROM workflowmemory
                WHERE workflow_id = :workflow_id
                AND conversation_id = :conversation_id
            """)
            result = await db.execute(delete_query, {
                "workflow_id": workflow_id,
                "conversation_id": conversation_id
            })
            deleted_count = result.rowcount

        await db.commit()

        return {
            "status": "success",
            "operation": "delete memory",
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} memories"
        }

    async def _prune_memories(
            self,
            db: AsyncSession,
            workflow_id: str,
            conversation_id: str,
            data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Manual memory pruning based on age or count.
        """
        retention_days = int(data.get("retention_days", MemoryConfig.DEFAULT_RETENTION_DAYS))
        max_memories = int(data.get("max_memories", MemoryConfig.DEFAULT_MAX_MEMORIES_PER_CONVERSATION))

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # 1. Delete old memories
        age_delete_query = text("""
            DELETE FROM workflowmemory
            WHERE workflow_id = :workflow_id
            AND conversation_id = :conversation_id
            AND created_at < :cutoff_date
        """)

        age_result = await db.execute(age_delete_query, {
            "workflow_id": workflow_id,
            "conversation_id": conversation_id,
            "cutoff_date": cutoff_date
        })
        age_deleted = age_result.rowcount

        # 2. Check if still over limit
        count_query = text("""
            SELECT COUNT(*) FROM workflowmemory
            WHERE workflow_id = :workflow_id
            AND conversation_id = :conversation_id
        """)

        result = await db.execute(count_query, {
            "workflow_id": workflow_id,
            "conversation_id": conversation_id
        })
        current_count = result.scalar() or 0

        count_deleted = 0
        if current_count > max_memories:
            # Delete oldest to get under limit
            to_delete = current_count - max_memories

            count_delete_query = text("""
                DELETE FROM workflowmemory
                WHERE id IN (
                    SELECT id FROM workflowmemory
                    WHERE workflow_id = :workflow_id
                    AND conversation_id = :conversation_id
                    ORDER BY created_at ASC
                    LIMIT :to_delete
                )
            """)

            count_result = await db.execute(count_delete_query, {
                "workflow_id": workflow_id,
                "conversation_id": conversation_id,
                "to_delete": to_delete
            })
            count_deleted = count_result.rowcount

        await db.commit()

        total_deleted = age_deleted + count_deleted

        return {
            "status": "success",
            "operation": "prune memories",
            "deleted_by_age": age_deleted,
            "deleted_by_count": count_deleted,
            "total_deleted": total_deleted,
            "remaining_count": current_count - count_deleted,
            "cutoff_date": cutoff_date.isoformat()
        }

    async def _get_stats(
            self,
            db: AsyncSession,
            workflow_id: str,
            conversation_id: str
    ) -> Dict[str, Any]:
        """
        Returns memory usage statistics.
        """
        stats_query = text("""
            SELECT 
                COUNT(*) as total_memories,
                SUM(LENGTH(content)) as total_chars,
                MIN(created_at) as oldest_memory,
                MAX(created_at) as newest_memory,
                COUNT(DISTINCT role) as unique_roles
            FROM workflowmemory
            WHERE workflow_id = :workflow_id
            AND conversation_id = :conversation_id
        """)

        result = await db.execute(stats_query, {
            "workflow_id": workflow_id,
            "conversation_id": conversation_id
        })
        row = result.fetchone()

        total_chars = row[1] or 0
        estimated_tokens = total_chars // MemoryConfig.CHARS_PER_TOKEN

        # Get role breakdown
        role_query = text("""
            SELECT role, COUNT(*) as count
            FROM workflowmemory
            WHERE workflow_id = :workflow_id
            AND conversation_id = :conversation_id
            GROUP BY role
        """)

        role_result = await db.execute(role_query, {
            "workflow_id": workflow_id,
            "conversation_id": conversation_id
        })
        role_breakdown = {r[0]: r[1] for r in role_result.fetchall()}

        return {
            "status": "success",
            "operation": "get stats",
            "stats": {
                "total_memories": row[0] or 0,
                "total_characters": total_chars,
                "estimated_tokens": estimated_tokens,
                "oldest_memory": row[2].isoformat() if row[2] else None,
                "newest_memory": row[3].isoformat() if row[3] else None,
                "role_breakdown": role_breakdown,
                "workflow_id": workflow_id,
                "conversation_id": conversation_id
            }
        }