import asyncio
import logging
import time
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

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
    # Added:
    "jamanetwork.com",
    "cochrane.org",
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

LLM_CLASSIFY_PROMPT = """You are a source credibility classifier. Given a domain name, URL, and content snippet from a search result, classify the source into one of three tiers:

- "high": Academic institutions, government agencies, peer-reviewed journals, major international organizations
- "mid": Established news organizations, reputable encyclopedias, well-known fact-checking sites, major industry publications
- "low": Personal blogs, marketing sites, unknown domains, user-generated content, vendor content

Return a JSON object:
{
  "tier": "high" | "mid" | "low",
  "reasoning": "One-sentence explanation"
}

Return ONLY the JSON object."""


def _classify_url(url: str) -> str:
    """Return 'high', 'mid', or 'low' tier for a given URL (heuristic only)."""
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


async def _classify_url_with_fallback(
    url: str, title: str, snippet: str, llm, cb, run_id: str
) -> tuple[str, str]:
    """Return (tier, method) where method is 'heuristic' or 'llm'."""
    tier = _classify_url(url)
    if tier != "low":
        return tier, "heuristic"

    # LLM fallback for unknown domains
    try:
        hostname = urlparse(url).hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]

        messages = [
            SystemMessage(content=LLM_CLASSIFY_PROMPT),
            HumanMessage(content=f"Domain: {hostname}\nURL: {url}\nTitle: {title}\nSnippet: {snippet[:200]}"),
        ]
        response = await llm.ainvoke(messages)
        parsed = parse_llm_json(response.content.strip())
        llm_tier = parsed.get("tier", "low").lower()
        if llm_tier in ("high", "mid", "low"):
            return llm_tier, "llm"
    except Exception as e:
        logger.warning(f"[{run_id}] [classify] LLM fallback failed for {url}: {e}")

    return "low", "heuristic"


async def classify_node(state: VerificationState) -> dict:
    """Node 5: Classify each search result URL into a credibility tier.

    Uses heuristic domain lists first; falls back to LLM for unknown low-tier domains.
    All results classified concurrently.
    """
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [classify] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        await cb.aemit({
            "type": "node_event",
            "node": "classify",
            "status": "running",
            "detail": "Classifying sources by credibility tier...",
        })

    try:
        results = state.get("search_results", [])
        llm = get_llm(complexity="standard")

        async def classify_single(result: dict) -> dict:
            url = result.get("url", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")

            tier, method = await _classify_url_with_fallback(url, title, snippet, llm, cb, run_id)

            classified_result = dict(result)
            classified_result["source_tier"] = tier

            if cb:
                try:
                    domain = urlparse(url).hostname or url
                    domain = domain[4:] if domain.startswith("www.") else domain
                except Exception:
                    domain = url
                await cb.aemit({
                    "type": "node_event",
                    "node": "classify",
                    "status": "running",
                    "detail": f"Source classified: {domain} → {tier.upper()} tier ({method})",
                    "data": {"url": url, "domain": domain, "tier": tier, "method": method},
                })

            return classified_result

        # Classify all results concurrently (heuristic results return instantly;
        # only low-tier unknowns trigger LLM calls)
        classified = list(await asyncio.gather(*[classify_single(r) for r in results]))

        tier_counts = {"high": 0, "mid": 0, "low": 0}
        for r in classified:
            tier_counts[r.get("source_tier", "low")] += 1

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [classify] Classified {len(classified)} sources "
            f"(high={tier_counts['high']}, mid={tier_counts['mid']}, low={tier_counts['low']}) "
            f"in {elapsed:.2f}s"
        )

        if cb:
            await cb.aemit({
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
            await cb.aemit({
                "type": "node_event",
                "node": "classify",
                "status": "error",
                "detail": f"Classification failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"classify: {str(e)}")
        return {"classified_results": state.get("search_results", []), "errors": errors}
