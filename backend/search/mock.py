"""Mock search client returning realistic hardcoded results for development/testing.

Used when SEARCH_PROVIDER=mock — allows the full pipeline to run without
a real search API key. For production, use SEARCH_PROVIDER=serper with a
real SEARCH_API_KEY.
"""

import logging
import re

from backend.search.base import SearchClient

logger = logging.getLogger(__name__)

# Template search results covering common fact-checking topics
_MOCK_RESULTS_LIBRARY = {
    "earth sun orbit": [
        {"url": "https://nasa.gov/solar-system/sun", "title": "Our Sun – NASA Solar System Exploration", "snippet": "Earth orbits the Sun at an average distance of about 93 million miles (150 million km). Earth completes one orbit every 365.25 days."},
        {"url": "https://britannica.com/science/solar-system", "title": "Solar System | Definition, Planets, & Facts | Britannica", "snippet": "The solar system consists of the Sun and everything that orbits around it. Earth is the third planet from the Sun."},
        {"url": "https://apnews.com/science/heliocentric-model", "title": "Heliocentric model confirmed – AP News", "snippet": "The heliocentric model, placing the Sun at the center of the solar system with Earth in orbit around it, has been confirmed by centuries of astronomical observation."},
    ],
    "water boil 100": [
        {"url": "https://nist.gov/pml/water-properties", "title": "Properties of Water – NIST", "snippet": "At standard atmospheric pressure (1 atm, 101.3 kPa) at sea level, pure water boils at exactly 100°C (212°F)."},
        {"url": "https://chemlibre.ucr.edu/boiling_point", "title": "Boiling Point – Chemistry LibreTexts", "snippet": "The boiling point of a liquid is the temperature at which its vapor pressure equals the surrounding pressure. For water at sea level, this is 100°C (212°F)."},
        {"url": "https://britannica.com/science/boiling-point", "title": "Boiling Point | Definition & Facts | Britannica", "snippet": "Water boils at 100°C at sea level. At higher altitudes, where atmospheric pressure is lower, water boils at lower temperatures."},
    ],
    "great wall china space": [
        {"url": "https://nasa.gov/great-wall-china", "title": "Can You See the Great Wall of China from Space? – NASA", "snippet": "The Great Wall of China is not visible from space with the naked eye. NASA and multiple astronauts have confirmed this is a common myth."},
        {"url": "https://snopes.com/fact-check/great-wall-china-space", "title": "Is the Great Wall of China Visible from Space? | Snopes.com", "snippet": "FALSE: The claim that the Great Wall of China is visible from space with the naked eye has been widely debunked. The wall is too narrow to be seen at orbital altitudes."},
        {"url": "https://bbc.com/news/great-wall-china-myth", "title": "The Great Wall of China space myth debunked – BBC News", "snippet": "Chinese astronaut Yang Liwei confirmed he could not see the Great Wall from space during China's first crewed spaceflight. Scientists agree the wall is too narrow to be visible."},
        {"url": "https://scientificamerican.com/great-wall-space-myth", "title": "Great Wall of China Space Visibility: Scientific American", "snippet": "At the altitude of the International Space Station (400 km), the minimum width needed to see an object with the naked eye would be about 10 km. The Great Wall is only about 15-30 feet wide."},
    ],
    "default": [
        {"url": "https://reuters.com/fact-check", "title": "Reuters Fact Check", "snippet": "Reuters fact-check team verifies claims with independent sources and scientific evidence."},
        {"url": "https://apnews.com/hub/fact-check", "title": "AP Fact Check – Associated Press", "snippet": "The Associated Press fact check team investigates claims circulating in public discourse."},
        {"url": "https://britannica.com/topic", "title": "Encyclopaedia Britannica", "snippet": "Encyclopaedia Britannica provides authoritative information on science, history, and current events."},
        {"url": "https://pbs.org/news/science", "title": "PBS NewsHour – Science", "snippet": "PBS NewsHour provides trusted news and science reporting from leading experts."},
        {"url": "https://npr.org/sections/science", "title": "Science : NPR", "snippet": "NPR Science covers discoveries, research, and science news from around the world."},
    ],
}


def _pick_results(query: str) -> list[dict]:
    """Select mock results relevant to the query."""
    q = query.lower()
    if ("earth" in q or "planet" in q) and ("sun" in q or "orbit" in q or "revolve" in q):
        return _MOCK_RESULTS_LIBRARY["earth sun orbit"]
    if ("water" in q or "h2o" in q) and ("boil" in q or "100" in q or "celsius" in q):
        return _MOCK_RESULTS_LIBRARY["water boil 100"]
    if ("great wall" in q or "china" in q) and ("space" in q or "orbit" in q or "visible" in q):
        return _MOCK_RESULTS_LIBRARY["great wall china space"]
    return _MOCK_RESULTS_LIBRARY["default"]


class MockSearchClient(SearchClient):
    """Hardcoded mock search client for development/testing without a real search API."""

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        results = _pick_results(query)[:num_results]
        logger.debug(f"[mock_search] Query '{query}' -> {len(results)} mock results")
        return results
