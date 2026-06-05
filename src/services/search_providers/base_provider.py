from abc import ABC, abstractmethod
from typing import List, Dict, Any
from loguru import logger
import httpx

class AbstractSearchProvider(ABC):
    """
    Abstract base class for all web search providers.
    Defines the interface for performing a search and checking configuration.
    """
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @property
    @abstractmethod
    def name(self) -> str:
        """The user-friendly name of the provider."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the necessary API keys or tokens are available."""
        pass

    @abstractmethod
    async def search(self, query: str) -> List[Dict[str, Any]]:
        """Perform the search and return a standardized list of results."""
        pass

    def _log_success(self, query: str):
        logger.success(f"Successfully retrieved search results from {self.name} for query: '{query}'.")

    def _log_failure(self, query: str, error: Exception):
        logger.warning(f"{self.name} search failed for query '{query}': {error}. Trying next provider.")