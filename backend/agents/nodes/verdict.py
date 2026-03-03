import json
import logging
import time
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a verdict assignment assistant. Given a claim and its weighted evidence, assign a validity verdict.

Verdict definitions:
- "high": Strong weighted support from credible sources (high/mid tier), with no significant contradictions.
- "medium": Mixed evidence, or support only from low-tier sources, or insufficient evidence to reach a confident conclusion.
- "low": Weak or no support, or contradicted by credible sources.
- "contradicted": High-tier or mid-tier sources directly contradict the claim.

Also assign a confidence score (0.0–1.0) reflecting your certainty in the verdict.

Return a JSON object with this exact structure:
{
  "verdict": "high" | "medium" | "low" | "contradicted",
  "confidence": 0.0–1.0,
  "reasoning": "One-sentence explanation of the verdict."
}

Return ONLY the JSON object, no other text."""


def verdict_node(state: VerificationState) -> dict:
    """Node 7: Assign a validity verdict per claim based on weighted evidence."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [verdict] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        cb.emit({
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

        claim_verdicts = []

        for claim in approved_claims:
            claim_id = claim["id"]
            claim_text = claim["text"]
            assessments = evidence_by_claim.get(claim_id, [])
            sources = sources_by_claim.get(claim_id, [])

            if cb:
                claim_preview = claim_text[:80] + "..." if len(claim_text) > 80 else claim_text
                cb.emit({
                    "type": "node_event",
                    "node": "verdict",
                    "status": "running",
                    "detail": f"Assigning verdict for: \"{claim_preview}\"",
                    "data": {"claim_id": claim_id},
                })

            # Summarise evidence for the LLM
            evidence_summary = []
            for a in assessments:
                evidence_summary.append({
                    "assessment": a["assessment"],
                    "reasoning": a["reasoning"],
                    "weight": a["weight"],
                    "source_tier": a["source"].get("source_tier", "low"),
                    "url": a["source"].get("url", ""),
                })

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
                response = llm.invoke(messages)
                content = response.content.strip()

                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                parsed = json.loads(content)
                verdict = parsed.get("verdict", "medium")
                confidence = float(parsed.get("confidence", 0.5))

            except Exception as e:
                logger.warning(f"[{run_id}] [verdict] Failed for claim {claim_id}: {e}")
                verdict = "medium"
                confidence = 0.3

            # Split evidence into supporting and contradicting
            supporting = [a for a in assessments if a["assessment"] == "supports"]
            contradicting = [a for a in assessments if a["assessment"] == "contradicts"]

            claim_verdicts.append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "verdict": verdict,
                "confidence": confidence,
                "supporting_evidence": supporting,
                "contradicting_evidence": contradicting,
                "sources": sources,
            })

            logger.debug(
                f"[{run_id}] [verdict] Claim '{claim_text[:50]}...' -> {verdict} ({confidence:.2f})"
            )

            if cb:
                cb.emit({
                    "type": "node_event",
                    "node": "verdict",
                    "status": "completed",
                    "detail": f"Verdict: {verdict.upper()} (confidence: {confidence:.0%})",
                    "data": {"claim_id": claim_id, "verdict": verdict, "confidence": confidence},
                })

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [verdict] Assigned verdicts for {len(claim_verdicts)} claims in {elapsed:.2f}s"
        )

        return {"claim_verdicts": claim_verdicts}

    except Exception as e:
        logger.exception(f"[{run_id}] [verdict] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "verdict",
                "status": "error",
                "detail": f"Verdict assignment failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"verdict: {str(e)}")
        return {"claim_verdicts": [], "errors": errors}
