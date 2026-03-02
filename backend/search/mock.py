"""Mock search client that uses an LLM to generate realistic search results.

This is used when SEARCH_PROVIDER=mock — useful for development/testing in
environments where real search APIs are not available. The LLM generates
plausible search results with realistic URLs and snippets.

NOTE: This does NOT constitute real verification — it is for development and
demonstration only. Set SEARCH_PROVIDER=serper with a real API key for
production use.
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from backend.search.base import SearchClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are simulating a web search engine for development/testing purposes. Given a search query, generate realistic-looking search results that a real search engine would return.

Generate exactly {num_results} realistic search results. For each result provide:
- A realistic URL from a credible source (use real domain names like reuters.com, bbc.com, nasa.gov, britannica.com, etc.)
- A realistic title
- A realistic snippet (1-2 sentences of text that would appear in a search result)

The results should reflect what real web pages would say about the query topic. For factual topics, reflect the scientific or journalistic consensus.

Return a JSON object with this exact structure:
{{
  "results": [
    {{"url": "https://example.com/page", "title": "Page Title", "snippet": "Relevant snippet text..."}},
    ...
  ]
}}

Return ONLY the JSON object, no other text."""


class MockSearchClient(SearchClient):
    """LLM-powered mock search client for development/testing."""

    def __init__(self):
        # Import here to avoid circular import
        from backend.config import get_llm
        self._get_llm = get_llm

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        """Generate mock search results using an LLM."""
        try:
            # Use standard model for mock search — cheaper and sufficient
            llm = self._get_llm(complexity="standard")

            messages = [
                SystemMessage(content=SYSTEM_PROMPT.format(num_results=num_results)),
                HumanMessage(content=f"Generate {num_results} search results for: {query}"),
            ]

            response = llm.invoke(messages)
            content = response.content.strip()

            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            parsed = json.loads(content)
            results = parsed.get("results", [])[:num_results]

            logger.debug(f"[mock_search] Query '{query}' -> {len(results)} mock results")
            return results

        except Exception as e:
            logger.warning(f"[mock_search] Failed for '{query}': {e}")
            return []
