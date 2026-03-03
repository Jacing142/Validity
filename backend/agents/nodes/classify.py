import logging
import time
from urllib.parse import urlparse

from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback

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
    cb = get_callback(run_id)

    if cb:
        cb.emit({
            "type": "node_event",
            "node": "classify",
            "status": "running",
            "detail": "Classifying sources by credibility tier...",
        })

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

            # Emit per-source classification event
            if cb:
                url = result.get("url", "")
                try:
                    from urllib.parse import urlparse as _up
                    domain = _up(url).hostname or url
                    domain = domain[4:] if domain.startswith("www.") else domain
                except Exception:
                    domain = url
                cb.emit({
                    "type": "node_event",
                    "node": "classify",
                    "status": "running",
                    "detail": f"Source classified: {domain} → {tier.upper()} tier",
                    "data": {"url": url, "domain": domain, "tier": tier},
                })

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [classify] Classified {len(classified)} sources "
            f"(high={tier_counts['high']}, mid={tier_counts['mid']}, low={tier_counts['low']}) "
            f"in {elapsed:.2f}s"
        )

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "classify",
                "status": "completed",
                "detail": (
                    f"Classified {len(classified)} sources: "
                    f"{tier_counts['high']} high, {tier_counts['mid']} mid, {tier_counts['low']} low"
                ),
                "data": tier_counts,
            })

        return {"classified_results": classified}

    except Exception as e:
        logger.exception(f"[{run_id}] [classify] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "classify",
                "status": "error",
                "detail": f"Classification failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"classify: {str(e)}")
        return {"classified_results": state.get("search_results", []), "errors": errors}
