import asyncio
from typing import List, Dict, Any
from serpapi import GoogleSearch
from src.core.settings import system_setting
from .base_provider import AbstractSearchProvider

class SerpApiProvider(AbstractSearchProvider):
    """Search provider implementation for SerpApi."""

    @property
    def name(self) -> str:
        return "SerpApi"

    def is_configured(self) -> bool:
        return bool(getattr(system_setting, 'SERPAPI_API_KEY', None))

    async def search(self, query: str) -> List[Dict[str, Any]]:
        api_key = getattr(system_setting, 'SERPAPI_API_KEY')

        def search_sync():
            """Synchronous function to be run in a thread."""
            params = {"q": query, "api_key": api_key, "engine": "google"}
            search = GoogleSearch(params)
            results = search.get_dict()
            return results.get("organic_results", [])

        loop = asyncio.get_event_loop()
        organic_results = await loop.run_in_executor(None, search_sync)

        if not organic_results: return []

        self._log_success(query)
        return [{"title": r.get("title"), "link": r.get("link")} for r in organic_results[:5]]