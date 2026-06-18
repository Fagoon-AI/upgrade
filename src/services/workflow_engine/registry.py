import threading
import importlib
import inspect
from typing import Dict, Type, List, Optional, Set, Any
from datetime import datetime, timezone
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode


class NodeNotFoundError(Exception):
    """Raised when requested node type doesn't exist."""

    def __init__(self, node_type: str):
        super().__init__(f"Node type '{node_type}' is not registered")
        self.node_type = node_type


class NodeRegistry:
    """
    Thread-Safe Node Registry.

    BACKWARD COMPATIBILITY:
    - register(node_class) works exactly as before
    - get_node(node_type) works exactly as before

    New Features:
    - Thread-safe registration
    - Manifest caching
    - Category indexing
    - Hot-reload support
    - Statistics and monitoring

    Usage (Existing - Still Works):
        NodeRegistry.register(MyNode)
        node = NodeRegistry.get_node("myNode")

    Usage (Enhanced):
        registry = NodeRegistry.get_instance()
        registry.register(MyNode)
        all_manifests = registry.list_manifests()
    """

    # Class-level storage (backward compatible)
    _registry: Dict[str, Type[BaseNode]] = {}

    # New: Thread safety
    _lock = threading.RLock()

    # New: Manifest cache
    _manifest_cache: Dict[str, Dict[str, Any]] = {}

    # New: Category index
    _categories: Dict[str, Set[str]] = {}

    # New: Registration metadata
    _registration_info: Dict[str, Dict[str, Any]] = {}

    # Singleton instance
    _instance: Optional['NodeRegistry'] = None

    def __new__(cls) -> 'NodeRegistry':
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'NodeRegistry':
        """Returns the singleton registry instance."""
        return cls()

    # EXISTING INTERFACE (DO NOT MODIFY SIGNATURES)

    @classmethod
    def register(cls, node_class: Type[BaseNode]) -> None:
        """
        Registers a node class with the registry.

        BACKWARD COMPATIBLE: Signature unchanged.
        ENHANCED: Now thread-safe with metadata tracking.

        Args:
            node_class: The node class to register
        """
        with cls._lock:
            node_type = node_class.node_type

            # Store in registry
            cls._registry[node_type] = node_class

            # Cache manifest
            try:
                manifest = node_class.get_manifest()
                cls._manifest_cache[node_type] = manifest

                # Index by category
                category = manifest.get("category", "Utilities")
                if category not in cls._categories:
                    cls._categories[category] = set()
                cls._categories[category].add(node_type)
            except Exception as e:
                # Manifest is optional, log but don't fail
                logger.debug(f"Could not cache manifest for {node_type}: {e}")

            # Track registration info
            cls._registration_info[node_type] = {
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "module": node_class.__module__,
                "class_name": node_class.__name__
            }

            logger.debug(f"✅ Registered node: {node_type}")

    @classmethod
    def get_node(cls, node_type: str) -> BaseNode:
        """
        Returns a new instance of the requested node type.

        BACKWARD COMPATIBLE: Signature unchanged.
        ENHANCED: Better error message.

        Args:
            node_type: The node type identifier

        Returns:
            New instance of the node class

        Raises:
            ValueError: If node type isn't registered (backward compatible)
        """
        with cls._lock:
            node_class = cls._registry.get(node_type)
            if not node_class:
                raise ValueError(f"Node type '{node_type}' is not supported.")
            return node_class()

    # NEW METHODS (Additive - don't break existing code)

    @classmethod
    def get_node_class(cls, node_type: str) -> Type[BaseNode]:
        """
        Returns the class (not instance) for a node type.
        NEW METHOD: For inspection without instantiation.
        """
        with cls._lock:
            node_class = cls._registry.get(node_type)
            if not node_class:
                raise NodeNotFoundError(node_type)
            return node_class

    @classmethod
    def has_node(cls, node_type: str) -> bool:
        """
        Checks if a node type is registered.
        NEW METHOD: Safer than catching exceptions.
        """
        return node_type in cls._registry

    @classmethod
    def unregister(cls, node_type: str) -> bool:
        """
        Removes a node type from the registry.
        NEW METHOD: For hot-reload support.

        Returns:
            True if removed, False if wasn't registered
        """
        with cls._lock:
            if node_type in cls._registry:
                del cls._registry[node_type]
                cls._manifest_cache.pop(node_type, None)
                cls._registration_info.pop(node_type, None)

                # Clean up category index
                for cat_nodes in cls._categories.values():
                    cat_nodes.discard(node_type)

                logger.debug(f"🗑️ Unregistered node: {node_type}")
                return True
            return False

    @classmethod
    def get_manifest(cls, node_type: str) -> Dict[str, Any]:
        """
        Returns the cached manifest for a node type.
        NEW METHOD: Fast path for manifest access.
        """
        with cls._lock:
            manifest = cls._manifest_cache.get(node_type)
            if manifest:
                return manifest

            # Fallback: generate manifest
            node_class = cls._registry.get(node_type)
            if not node_class:
                raise NodeNotFoundError(node_type)

            manifest = node_class.get_manifest()
            cls._manifest_cache[node_type] = manifest
            return manifest

    @classmethod
    def list_nodes(cls) -> List[str]:
        """
        Returns all registered node types.
        NEW METHOD: For discovery.
        """
        with cls._lock:
            return list(cls._registry.keys())

    @classmethod
    def list_manifests(cls, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns all registered node manifests.
        NEW METHOD: For frontend node library.

        Args:
            category: Optional filter by category
        """
        with cls._lock:
            manifests = []

            for node_type in cls._registry.keys():
                try:
                    manifest = cls.get_manifest(node_type)

                    if category and manifest.get("category") != category:
                        continue

                    manifests.append(manifest)
                except Exception:
                    continue

            # Sort by category, then display name
            return sorted(
                manifests,
                key=lambda m: (m.get("category", ""), m.get("display_name", ""))
            )

    @classmethod
    def list_categories(cls) -> List[str]:
        """
        Returns all registered categories.
        NEW METHOD: For UI organization.
        """
        with cls._lock:
            return sorted(cls._categories.keys())

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """
        Returns registry statistics.

        NEW METHOD: For monitoring.
        """
        with cls._lock:
            return {
                "total_nodes": len(cls._registry),
                "categories": len(cls._categories),
                "nodes_by_category": {
                    cat: len(nodes)
                    for cat, nodes in cls._categories.items()
                }
            }

    @classmethod
    def clear(cls) -> None:
        """
        Clears all registrations.
        NEW METHOD: For testing only.
        """
        with cls._lock:
            cls._registry.clear()
            cls._manifest_cache.clear()
            cls._categories.clear()
            cls._registration_info.clear()
            logger.warning("Node registry cleared")


# AUTO-REGISTRATION (Existing pattern preserved)
from src.services.workflow_engine.nodes.start import StartNode
from src.services.workflow_engine.nodes.tool_gmail import GmailNode
from src.services.workflow_engine.nodes.tool_gemini import GeminiNode
from src.services.workflow_engine.nodes.logic_filter import FilterNode
from src.services.workflow_engine.nodes.logic_wait import WaitNode
from src.services.workflow_engine.nodes.logic_loop import LoopNode
from src.services.workflow_engine.nodes.tool_memory import MemoryNode
from src.services.workflow_engine.nodes.tool_code import CodeExecutionNode
from src.services.workflow_engine.nodes.tool_rag import RAGNode
from src.services.workflow_engine.nodes.logic_router import RouterNode
from src.services.workflow_engine.nodes.tool_mistral_parse import MistralParseNode
from src.services.workflow_engine.nodes.tool_supabase import SupabaseNode
from src.services.workflow_engine.nodes.tool_slack import SlackNode
from src.services.workflow_engine.nodes.tool_browser_use import BrowserUseNode
from src.services.workflow_engine.nodes.tool_google_sheets import GoogleSheetsNode
from src.services.workflow_engine.nodes.logic_parallel import ParallelNode
from src.services.workflow_engine.nodes.tool_youtube import YouTubeNode
from src.services.workflow_engine.nodes.tool_perplexity import PerplexityNode
from src.services.workflow_engine.nodes.tool_agent import AgentNode
from src.services.workflow_engine.nodes.tool_webhook import WebhookNode
from src.services.workflow_engine.nodes.tool_openai import OpenAINode
from src.services.workflow_engine.nodes.tool_anthropic import AnthropicNode
from src.services.workflow_engine.nodes.trigger_schedule import ScheduleTriggerNode
from src.services.workflow_engine.nodes.tool_notion import NotionNode
from src.services.workflow_engine.nodes.tool_discord import DiscordNode
from src.services.workflow_engine.nodes.tool_twilio import TwilioNode

# Register all nodes (existing pattern)
NodeRegistry.register(StartNode)
NodeRegistry.register(GmailNode)
NodeRegistry.register(GeminiNode)
NodeRegistry.register(FilterNode)
NodeRegistry.register(LoopNode)
NodeRegistry.register(MemoryNode)
NodeRegistry.register(CodeExecutionNode)
NodeRegistry.register(RAGNode)
NodeRegistry.register(WaitNode)
NodeRegistry.register(RouterNode)
NodeRegistry.register(MistralParseNode)
NodeRegistry.register(SupabaseNode)
NodeRegistry.register(SlackNode)
NodeRegistry.register(BrowserUseNode)
NodeRegistry.register(GoogleSheetsNode)
NodeRegistry.register(ParallelNode)
NodeRegistry.register(YouTubeNode)
NodeRegistry.register(PerplexityNode)
NodeRegistry.register(AgentNode)
NodeRegistry.register(WebhookNode)
NodeRegistry.register(OpenAINode)
NodeRegistry.register(AnthropicNode)
NodeRegistry.register(ScheduleTriggerNode)
NodeRegistry.register(NotionNode)
NodeRegistry.register(DiscordNode)
NodeRegistry.register(TwilioNode)


# CONVENIENCE FUNCTIONS

def get_registry() -> NodeRegistry:
    """Returns the global registry instance."""
    return NodeRegistry.get_instance()


def register_node(node_class: Type[BaseNode]) -> Type[BaseNode]:
    """
    Decorator for automatic node registration.

    Usage:
        @register_node
        class MyNode(BaseNode):
            node_type = "myNode"
            ...
    """
    NodeRegistry.register(node_class)
    return node_class


def get_node(node_type: str) -> BaseNode:
    """Convenience function to get a node instance."""
    return NodeRegistry.get_node(node_type)