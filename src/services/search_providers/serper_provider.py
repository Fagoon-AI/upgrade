import json
from typing import List, Dict, Any
from src.core.settings import system_setting
from .base_provider import AbstractSearchProvider

class SerperProvider(AbstractSearchProvider):
    """Search provider implementation for Google Serper."""

    @property
    def name(self) -> str:
        return "Serper"

    def is_configured(self) -> bool:
        return bool(getattr(system_setting, 'SERPER_API_KEY', None))

    async def search(self, query: str) -> List[Dict[str, Any]]:
        api_key = getattr(system_setting, 'SERPER_API_KEY')
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        payload = json.dumps({"q": query})

        response = await self.client.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        search_results = response.json().get("organic", [])

        if not search_results: return []

        self._log_success(query)
        return [{"title": r.get("title"), "link": r.get("link")} for r in search_results[:5]]