from backend.search.base import SearchClient


class TavilySearchClient(SearchClient):
    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        raise NotImplementedError(
            "Tavily search not yet implemented. Set SEARCH_PROVIDER=serper in .env"
        )
