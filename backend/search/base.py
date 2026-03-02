from abc import ABC, abstractmethod


class SearchClient(ABC):
    @abstractmethod
    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        """Returns list of {url, title, snippet}"""
        ...
