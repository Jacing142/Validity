import logging
import time
from urllib.parse import urlparse

from backend.agents.state import VerificationState

logger = logging.getLogger(__name__)

# High-credibility domains: academic, government, major peer-reviewed journals
HIGH_DOMAINS = {
    "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "nature.com",
    "science.org",
    "sciencemag.org",
    "thelancet.com",
    "nejm.org",
    "bmj.com",
    "cell.com",
    "pnas.org",
    "nih.gov",
    "who.int",
    "cdc.gov",
    "nasa.gov",
    "noaa.gov",
    "nist.gov",
}

HIGH_TLDS = {".gov", ".edu"}

# Mid-credibility domains: established news, wire services, reputable .org
MID_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "pbs.org",
    "nytimes.com",
    "washingtonpost.com",
    "theguardian.com",
    "wsj.com",
    "ft.com",
    "economist.com",
    "theatlantic.com",
    "time.com",
    "politico.com",
    "axios.com",
    "bloomberg.com",
    "forbes.com",
    "scientificamerican.com",
    "newscientist.com",
    "nationalgeographic.com",
    "smithsonianmag.com",
    "wikipedia.org",
    "britannica.com",
    "mayoclinic.org",
    "clevelandclinic.org",
    "webmd.com",
    "healthline.com",
    "snopes.com",
    "factcheck.org",
    "politifact.com",
}


def _classify_url(url: str) -> str:
    """Return 'high', 'mid', or 'low' tier for a given URL."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Normalise: strip www.
        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Check exact domain match — high tier
        if hostname in HIGH_DOMAINS:
            return "high"

        # Check TLD — .gov and .edu are high
        for tld in HIGH_TLDS:
            if hostname.endswith(tld):
                return "high"

        # Check exact domain — mid tier
        if hostname in MID_DOMAINS:
            return "mid"

        # .org not already classified above defaults to mid
        if hostname.endswith(".org"):
            return "mid"

        return "low"

    except Exception:
        return "low"


def classify_node(state: VerificationState) -> dict:
    """Node 5: Classify each search result URL into a credibility tier (no LLM call)."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [classify] Entering node")
    start = time.time()

    try:
        results = state.get("search_results", [])

        classified = []
        tier_counts = {"high": 0, "mid": 0, "low": 0}
        for result in results:
            tier = _classify_url(result.get("url", ""))
            classified_result = dict(result)
            classified_result["source_tier"] = tier
            classified.append(classified_result)
            tier_counts[tier] += 1

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [classify] Classified {len(classified)} sources "
            f"(high={tier_counts['high']}, mid={tier_counts['mid']}, low={tier_counts['low']}) "
            f"in {elapsed:.2f}s"
        )

        return {"classified_results": classified}

    except Exception as e:
        logger.exception(f"[{run_id}] [classify] Failed")
        errors = list(state.get("errors", []))
        errors.append(f"classify: {str(e)}")
        return {"classified_results": state.get("search_results", []), "errors": errors}
