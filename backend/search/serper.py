import logging

import httpx

from backend.search.base import SearchClient

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"


class SerperSearchClient(SearchClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        """Search using Serper (Google Search API). Returns list of {url, title, snippet}."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    SERPER_URL,
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": num_results},
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "url": item.get("link", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                })

            logger.debug(f"[serper] Query '{query}' -> {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"[serper] Search failed for '{query}': {e}")
            return []
