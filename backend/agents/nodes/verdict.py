import asyncio
import json
import logging
import time
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a verdict assignment assistant. Given a claim and its weighted evidence, assign a validity verdict.

Verdict definitions:
- "high": Strong support from multiple sources with no contradictions. Can be high if ALL available sources support the claim consistently, even if they are low-tier, provided there are no contradictions and the claim is a well-established fact.
- "medium": Mixed evidence, insufficient sources, or only 1-2 sources supporting with no contradictions.
- "low": Weak or no support, or contradicted by low-tier sources, or fewer than 2 supporting sources.
- "contradicted": Any high-tier or mid-tier sources directly contradict the claim, OR multiple low-tier sources contradict it.

Confidence score (0.0–1.0): reflects your certainty in the verdict.

Critical rules:
- If ALL sources support a claim and NONE contradict it, the verdict should be "high" or "medium" — never "low".
- "low" requires either active contradiction OR very few supporting sources (1 or fewer).
- Consistent agreement across multiple sources — even low-tier ones — is meaningful signal. 5+ sources all supporting with 0 contradictions = "high".
- Reserve "low" for genuine lack of support or active contradiction, not for cases where sources happen to be low-tier but all agree.

Return a JSON object with this exact structure:
{
  "verdict": "high" | "medium" | "low" | "contradicted",
  "confidence": 0.0–1.0,
  "reasoning": "One-sentence explanation of the verdict."
}

Return ONLY the JSON object, no other text."""

async def verdict_node(state: VerificationState) -> dict:
    """Node 7: Assign a validity verdict per claim based on weighted evidence (parallel per claim)."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [verdict] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        await cb.aemit({
            "type": "node_event",
            "node": "verdict",
            "status": "running",
            "detail": "Assigning verdicts based on evidence...",
        })

    try:
        evidence_assessments = state.get("evidence_assessments", [])
        approved_claims = state.get("approved_claims", [])
        classified_results = state.get("classified_results", [])

        if not approved_claims:
            logger.warning(f"[{run_id}] [verdict] No approved claims")
            return {"claim_verdicts": []}

        llm = get_llm(complexity="standard")

        # Group evidence by claim_id
        evidence_by_claim: dict[str, list[dict]] = defaultdict(list)
        for assessment in evidence_assessments:
            evidence_by_claim[assessment["claim_id"]].append(assessment)

        # Group sources by claim_id
        sources_by_claim: dict[str, list[dict]] = defaultdict(list)
        for result in classified_results:
            sources_by_claim[result["claim_id"]].append(result)

        async def verdict_single_claim(claim: dict) -> dict:
            """Assign verdict for a single claim; returns claim_verdict dict."""
            claim_id = claim["id"]
            claim_text = claim["text"]
            assessments = evidence_by_claim.get(claim_id, [])
            sources = sources_by_claim.get(claim_id, [])

            if cb:
                claim_preview = claim_text[:80] + "..." if len(claim_text) > 80 else claim_text
                await cb.aemit({
                    "type": "node_event",
                    "node": "verdict",
                    "status": "running",
                    "detail": f"Assigning verdict for: \"{claim_preview}\"",
                    "data": {"claim_id": claim_id},
                })

            # Summarise evidence for the LLM
            evidence_summary = [
                {
                    "assessment": a["assessment"],
                    "reasoning": a["reasoning"],
                    "weight": a["weight"],
                    "source_tier": a["source"].get("source_tier", "low"),
                    "url": a["source"].get("url", ""),
                }
                for a in assessments
            ]

            evidence_text = json.dumps(evidence_summary, indent=2)

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Claim: {claim_text}\n\n"
                        f"Weighted evidence:\n{evidence_text}"
                    )
                ),
            ]

            try:
                response = await llm.ainvoke(messages)
                content = response.content.strip()
                parsed = parse_llm_json(content)
                verdict = parsed.get("verdict", "medium")
                confidence = float(parsed.get("confidence", 0.5))
            except Exception as e:
                logger.warning(f"[{run_id}] [verdict] Failed for claim {claim_id}: {e}")
                verdict = "medium"
                confidence = 0.3

            # Split evidence into supporting and contradicting
            supporting = [a for a in assessments if a["assessment"] == "supports"]
            contradicting = [a for a in assessments if a["assessment"] == "contradicts"]

            logger.debug(
                f"[{run_id}] [verdict] Claim '{claim_text[:50]}...' -> {verdict} ({confidence:.2f})"
            )

            if cb:
                await cb.aemit({
                    "type": "node_event",
                    "node": "verdict",
                    "status": "completed",
                    "detail": f"Verdict: {verdict.upper()} (confidence: {confidence:.0%})",
                    "data": {"claim_id": claim_id, "verdict": verdict, "confidence": confidence},
                })

            return {
                "claim_id": claim_id,
                "claim_text": claim_text,
                "verdict": verdict,
                "confidence": confidence,
                "supporting_evidence": supporting,
                "contradicting_evidence": contradicting,
                "sources": sources,
                "kept_original_subjective": claim.get("kept_original_subjective", False),
            }

        # Run all claims concurrently
        tasks = [verdict_single_claim(claim) for claim in approved_claims]
        claim_verdicts = list(await asyncio.gather(*tasks))

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [verdict] Assigned verdicts for {len(claim_verdicts)} claims in {elapsed:.2f}s"
        )

        return {"claim_verdicts": claim_verdicts}

    except Exception as e:
        logger.exception(f"[{run_id}] [verdict] Failed")
        if cb:
            await cb.aemit({
                "type": "node_event",
                "node": "verdict",
                "status": "error",
                "detail": f"Verdict assignment failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"verdict: {str(e)}")
        return {"claim_verdicts": [], "errors": errors}
