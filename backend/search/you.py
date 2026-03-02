from backend.search.base import SearchClient


class YouSearchClient(SearchClient):
    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        raise NotImplementedError(
            "You.com search not yet implemented. Set SEARCH_PROVIDER=serper in .env"
        )
