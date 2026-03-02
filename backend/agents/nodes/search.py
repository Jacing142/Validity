import asyncio
import logging
import time
from collections import defaultdict

from backend.config import get_search_client, settings
from backend.agents.state import VerificationState

logger = logging.getLogger(__name__)


def _dedup_by_url(results: list[dict]) -> list[dict]:
    """Deduplicate results by URL, keeping the first occurrence."""
    seen = set()
    deduped = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)
    return deduped


async def _execute_all_queries(
    search_client,
    queries: list[dict],
    num_results: int,
) -> list[dict]:
    """Execute all search queries concurrently and return tagged results."""

    async def run_query(query_obj: dict) -> list[dict]:
        results = await search_client.search(query_obj["query"], num_results=num_results)
        tagged = []
        for r in results:
            tagged.append({
                **r,
                "claim_id": query_obj["claim_id"],
                "query_intent": query_obj["intent"],
                "source_tier": None,
            })
        return tagged

    all_tasks = [run_query(q) for q in queries]
    results_nested = await asyncio.gather(*all_tasks, return_exceptions=True)

    all_results = []
    for idx, batch in enumerate(results_nested):
        if isinstance(batch, Exception):
            logger.warning(f"[search] Query #{idx} failed: {batch}")
        else:
            all_results.extend(batch)

    return all_results


async def search_node(state: VerificationState) -> dict:
    """Node 4: Execute all search queries concurrently, tag with intent and claim_id."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [search] Entering node")
    start = time.time()

    try:
        queries = state.get("search_queries", [])
        if not queries:
            logger.warning(f"[{run_id}] [search] No search queries")
            return {"search_results": []}

        search_client = get_search_client()
        num_results = settings.MAX_SOURCES_PER_CLAIM

        logger.info(f"[{run_id}] [search] Executing {len(queries)} queries concurrently")

        all_results = await _execute_all_queries(search_client, queries, num_results)

        # Deduplicate by URL within each claim
        by_claim: dict[str, list[dict]] = defaultdict(list)
        for r in all_results:
            by_claim[r["claim_id"]].append(r)

        deduped = []
        for claim_id, results in by_claim.items():
            deduped.extend(_dedup_by_url(results))

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [search] Got {len(all_results)} raw results, "
            f"{len(deduped)} after dedup in {elapsed:.2f}s"
        )

        return {"search_results": deduped}

    except Exception as e:
        logger.exception(f"[{run_id}] [search] Failed")
        errors = list(state.get("errors", []))
        errors.append(f"search: {str(e)}")
        return {"search_results": [], "errors": errors}
