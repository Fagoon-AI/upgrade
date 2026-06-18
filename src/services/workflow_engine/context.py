import asyncio
import copy
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone
from uuid import UUID
from enum import Enum, auto

from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
from loguru import logger


class ContextState(Enum):
    """Execution context lifecycle states."""
    INITIALIZING = auto()
    ACTIVE = auto()
    PAUSED = auto()
    FINALIZING = auto()
    COMPLETED = auto()
    FAILED = auto()


class ExecutionContext(BaseModel):
    """
    Shared Memory with Concurrency Protection.

    BACKWARD COMPATIBLE: All existing node code continues to work.

    Existing Interface (preserved):
    - workflow_id, execution_id, user_id
    - node_outputs dict
    - connections dict  
    - set_output(node_id, output)
    - get_output(node_id)

    New Features (additive):
    - State management with transitions
    - Scoped outputs for loop iterations
    - Execution metrics
    - Connection credential caching with security
    - Checkpoint/restore for resumption
    """

    # Pydantic configuration
    model_config = ConfigDict(arbitrary_types_allowed=True)
    workflow_id: str
    execution_id: str
    user_id: UUID
    node_outputs: Dict[str, Any] = Field(default_factory=dict)
    connections: Dict[str, Any] = Field(default_factory=dict)
    db_lock: asyncio.Lock = Field(default_factory=asyncio.Lock, exclude=True)
    # Global variables from workflow definition
    global_vars: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    # Scoped outputs for loop iterations
    _scoped_outputs: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)
    # State tracking
    _state: ContextState = PrivateAttr(default=ContextState.ACTIVE)
    _visited_nodes: Set[str] = PrivateAttr(default_factory=set)
    _pending_nodes: Set[str] = PrivateAttr(default_factory=set)
    # Execution metrics
    _metrics: Dict[str, Any] = PrivateAttr(default_factory=lambda: {
        "total_nodes_executed": 0,
        "total_retries": 0,
        "total_errors": 0,
        "total_duration_ms": 0
    })

    # Timestamps
    _created_at: datetime = PrivateAttr(default_factory=lambda: datetime.now(timezone.utc))
    _updated_at: datetime = PrivateAttr(default_factory=lambda: datetime.now(timezone.utc))

    # Fine-grained locks for new features
    _output_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _state_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)


    def set_output(self, node_id: str, output: Any) -> None:
        """
        Saves a node's result into the shared memory.
        """
        self.node_outputs[node_id] = output
        self._visited_nodes.add(node_id)
        self._pending_nodes.discard(node_id)
        self._metrics["total_nodes_executed"] += 1
        self._updated_at = datetime.now(timezone.utc)

    def get_output(self, node_id: str) -> Optional[Any]:
        """
        Retrieves a specific node's output from memory.
        """
        return self.node_outputs.get(node_id)

    async def set_output_async(
            self,
            node_id: str,
            output: Any,
            duration_ms: int = 0,
            error: Optional[str] = None,
            attempt_number: int = 1
    ) -> None:
        """
        Async version of set_output with enhanced tracking.
        """
        async with self._output_lock:
            self.node_outputs[node_id] = output
            self._visited_nodes.add(node_id)
            self._pending_nodes.discard(node_id)

            # Update metrics
            self._metrics["total_nodes_executed"] += 1
            self._metrics["total_duration_ms"] += duration_ms
            if error:
                self._metrics["total_errors"] += 1
            if attempt_number > 1:
                self._metrics["total_retries"] += (attempt_number - 1)

            self._updated_at = datetime.now(timezone.utc)

    async def set_scoped_output(
            self,
            node_id: str,
            scope_key: str,
            output: Any
    ) -> None:
        """
        Records output for loop iterations with scope isolation.

        Args:
            node_id: The node identifier
            scope_key: Unique key for this iteration (e.g., "item_0")
            output: The node's output data
        """
        async with self._output_lock:
            if node_id not in self._scoped_outputs:
                self._scoped_outputs[node_id] = {}
            self._scoped_outputs[node_id][scope_key] = copy.deepcopy(output)
            self._updated_at = datetime.now(timezone.utc)

    def get_scoped_outputs(self, node_id: str) -> Dict[str, Any]:
        """Returns all scoped outputs for a node (loop iterations)."""
        return copy.deepcopy(self._scoped_outputs.get(node_id, {}))

    def has_output(self, node_id: str) -> bool:
        """Check if a node has completed execution."""
        return node_id in self.node_outputs

    # STATE MANAGEMENT

    @property
    def state(self) -> ContextState:
        """Current execution state."""
        return self._state

    async def transition_state(self, new_state: ContextState) -> bool:
        """
        Validates and performs state transition.

        Returns True if transition was valid, False otherwise.
        """
        valid_transitions = {
            ContextState.INITIALIZING: {ContextState.ACTIVE, ContextState.FAILED},
            ContextState.ACTIVE: {ContextState.PAUSED, ContextState.FINALIZING, ContextState.FAILED},
            ContextState.PAUSED: {ContextState.ACTIVE, ContextState.FAILED},
            ContextState.FINALIZING: {ContextState.COMPLETED, ContextState.FAILED},
            ContextState.COMPLETED: set(),  # Terminal
            ContextState.FAILED: set()      # Terminal
        }

        async with self._state_lock:
            if new_state in valid_transitions.get(self._state, set()):
                old_state = self._state
                self._state = new_state
                self._updated_at = datetime.now(timezone.utc)
                logger.debug(f"Context state: {old_state.name} -> {new_state.name}")
                return True

            logger.warning(f"Invalid state transition: {self._state.name} -> {new_state.name}")
            return False

    async def mark_node_pending(self, node_id: str) -> None:
        """Marks a node as pending execution."""
        async with self._output_lock:
            self._pending_nodes.add(node_id)

    # CONNECTION CREDENTIAL CACHING

    def cache_connection(
            self,
            connection_id: str,
            credentials: Dict[str, Any]
    ) -> None:
        """
        Caches decrypted connection credentials for reuse.

        Security: Credentials cached in memory only for this execution.
        """
        self.connections[connection_id] = copy.deepcopy(credentials)

    def get_cached_connection(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached credentials.

        Returns None if not cached - caller should decrypt from DB.
        """
        creds = self.connections.get(connection_id)
        return copy.deepcopy(creds) if creds else None

    # METRICS & OBSERVABILITY

    @property
    def metrics(self) -> Dict[str, Any]:
        """Returns current execution metrics (defensive copy)."""
        return copy.deepcopy(self._metrics)

    @property
    def visited_nodes(self) -> Set[str]:
        """Returns set of visited node IDs."""
        return self._visited_nodes.copy()

    @property
    def pending_nodes(self) -> Set[str]:
        """Returns set of pending node IDs."""
        return self._pending_nodes.copy()

    # SERIALIZATION & CHECKPOINTING

    def to_checkpoint(self) -> Dict[str, Any]:
        """
        Serializes context state for persistence/recovery.

        Used for:
        - Saving context_data to database
        - Resuming paused executions
        """
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "user_id": str(self.user_id),
            "node_outputs": copy.deepcopy(self.node_outputs),
            "state": self._state.name,
            "visited_nodes": list(self._visited_nodes),
            "metrics": self._metrics,
            "updated_at": self._updated_at.isoformat()
        }

    @classmethod
    def from_checkpoint(
            cls,
            workflow_id: str,
            execution_id: str,
            user_id: UUID,
            checkpoint_data: Dict[str, Any]
    ) -> 'ExecutionContext':
        """
        Restores context from a checkpoint.

        Used for resuming paused executions.
        """
        context = cls(
            workflow_id=workflow_id,
            execution_id=execution_id,
            user_id=user_id,
            node_outputs=checkpoint_data.get("node_outputs", {})
        )

        # Restore state
        context._visited_nodes = set(checkpoint_data.get("visited_nodes", []))
        context._metrics = checkpoint_data.get("metrics", context._metrics)

        return context


# FACTORY FUNCTION

def create_execution_context(
        workflow_id: str,
        execution_id: str,
        user_id: UUID,
        global_vars: Optional[Dict[str, Any]] = None,
        checkpoint_data: Optional[Dict[str, Any]] = None
) -> ExecutionContext:
    """
    Factory function for creating ExecutionContext instances.

    Args:
        workflow_id: UUID of the workflow being executed
        execution_id: UUID of this specific execution
        user_id: UUID of the user who owns the workflow
        global_vars: Environment variables for the workflow
        checkpoint_data: Previous context_data for resumption

    Returns:
        Initialized ExecutionContext ready for use
    """
    if checkpoint_data:
        context = ExecutionContext.from_checkpoint(
            workflow_id=workflow_id,
            execution_id=execution_id,
            user_id=user_id,
            checkpoint_data=checkpoint_data
        )
    else:
        context = ExecutionContext(
            workflow_id=workflow_id,
            execution_id=execution_id,
            user_id=user_id
        )

    if global_vars:
        context.global_vars = copy.deepcopy(global_vars)

    return context