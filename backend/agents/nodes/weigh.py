import json
import logging
import time
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback

logger = logging.getLogger(__name__)

TIER_WEIGHTS = {"high": 1.0, "mid": 0.6, "low": 0.3}

SYSTEM_PROMPT = """You are an evidence analysis assistant. Given a claim and a list of sources with their snippets, assess each source.

For each source, determine:
1. **Assessment**: Does the source SUPPORT, CONTRADICT, or is it IRRELEVANT to the specific claim?
2. **Reasoning**: One-sentence explanation of why.

Be precise:
- SUPPORTS: the source provides evidence that the claim is true
- CONTRADICTS: the source provides evidence that the claim is false or challenges it
- IRRELEVANT: the source is about a related topic but doesn't address the specific claim

Return a JSON object with this exact structure:
{
  "assessments": [
    {
      "source_url": "<url>",
      "assessment": "supports" | "contradicts" | "irrelevant",
      "reasoning": "One sentence explanation."
    },
    ...
  ]
}

Return ONLY the JSON object, no other text."""


def weigh_node(state: VerificationState) -> dict:
    """Node 6: LLM assesses each source vs. its claim, applies tier-based weights."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [weigh] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        cb.emit({
            "type": "node_event",
            "node": "weigh",
            "status": "running",
            "detail": "Weighing evidence for each claim...",
        })

    try:
        classified_results = state.get("classified_results", [])
        approved_claims = state.get("approved_claims", [])

        if not classified_results or not approved_claims:
            logger.warning(f"[{run_id}] [weigh] No results or claims to weigh")
            return {"evidence_assessments": []}

        llm = get_llm(complexity="high")

        # Group results by claim_id
        by_claim: dict[str, list[dict]] = defaultdict(list)
        for result in classified_results:
            by_claim[result["claim_id"]].append(result)

        # Build lookup for claim text
        claim_map = {c["id"]: c["text"] for c in approved_claims}

        all_assessments = []

        for claim_id, sources in by_claim.items():
            claim_text = claim_map.get(claim_id, "Unknown claim")
            logger.debug(f"[{run_id}] [weigh] Weighing {len(sources)} sources for claim '{claim_text[:60]}...'")

            if cb:
                claim_preview = claim_text[:80] + "..." if len(claim_text) > 80 else claim_text
                cb.emit({
                    "type": "node_event",
                    "node": "weigh",
                    "status": "running",
                    "detail": f"Weighing evidence for: \"{claim_preview}\"",
                    "data": {"claim_id": claim_id},
                })

            sources_text = json.dumps(
                [{"url": s["url"], "title": s["title"], "snippet": s["snippet"]} for s in sources],
                indent=2,
            )

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Claim: {claim_text}\n\n"
                        f"Sources to assess:\n{sources_text}"
                    )
                ),
            ]

            try:
                response = llm.invoke(messages)
                content = response.content.strip()

                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                parsed = json.loads(content)
                assessments_by_url = {
                    a["source_url"]: a for a in parsed.get("assessments", [])
                }

                for source in sources:
                    url = source["url"]
                    assessment_data = assessments_by_url.get(url, {})
                    assessment = assessment_data.get("assessment", "irrelevant").lower()
                    reasoning = assessment_data.get("reasoning", "No reasoning provided.")
                    tier = source.get("source_tier", "low")
                    weight = TIER_WEIGHTS.get(tier, 0.3)

                    all_assessments.append({
                        "claim_id": claim_id,
                        "source": source,
                        "assessment": assessment,
                        "reasoning": reasoning,
                        "weight": weight,
                    })

            except Exception as e:
                logger.warning(f"[{run_id}] [weigh] Failed for claim {claim_id}: {e}")
                # Add all sources as irrelevant if LLM fails for this claim
                for source in sources:
                    tier = source.get("source_tier", "low")
                    all_assessments.append({
                        "claim_id": claim_id,
                        "source": source,
                        "assessment": "irrelevant",
                        "reasoning": f"Assessment failed: {str(e)}",
                        "weight": TIER_WEIGHTS.get(tier, 0.3),
                    })

        elapsed = time.time() - start
        num_claims = len(by_claim)
        logger.info(
            f"[{run_id}] [weigh] Assessed {len(all_assessments)} source-claim pairs in {elapsed:.2f}s"
        )

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "weigh",
                "status": "completed",
                "detail": f"Evidence weighed for {num_claims} claim{'s' if num_claims != 1 else ''}",
                "data": {"total_assessments": len(all_assessments)},
            })

        return {"evidence_assessments": all_assessments}

    except Exception as e:
        logger.exception(f"[{run_id}] [weigh] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "weigh",
                "status": "error",
                "detail": f"Evidence weighing failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"weigh: {str(e)}")
        return {"evidence_assessments": [], "errors": errors}
