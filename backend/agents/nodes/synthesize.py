import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a verification synthesis assistant. Given the per-claim verdicts from a fact-checking pipeline, produce an overall assessment.

Overall verdict options:
- "high": Most claims are well-supported by credible sources with little contradiction.
- "medium": Claims have mixed validity — some supported, some uncertain, none strongly contradicted.
- "low": Most claims lack credible support or are contradicted.
- "mixed": Claims vary significantly — some high validity, some low validity or contradicted.

Write a concise 2-3 sentence summary that:
1. States the overall finding
2. Highlights the most significant findings (especially any contradicted claims)
3. Notes the quality of evidence found

Return a JSON object with this exact structure:
{
  "verdict": "high" | "medium" | "low" | "mixed",
  "summary": "2-3 sentence natural language assessment."
}

Return ONLY the JSON object, no other text."""


def synthesize_node(state: VerificationState) -> dict:
    """Node 8: Synthesize per-claim verdicts into an overall verdict."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [synthesize] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        cb.emit({
            "type": "node_event",
            "node": "synthesize",
            "status": "running",
            "detail": "Synthesizing overall verdict...",
        })

    try:
        claim_verdicts = state.get("claim_verdicts", [])
        approved_claims = state.get("approved_claims", [])

        if not claim_verdicts:
            logger.warning(f"[{run_id}] [synthesize] No claim verdicts to synthesize")
            return {
                "overall_verdict": {
                    "summary": "No claims could be verified.",
                    "verdict": "low",
                    "claim_verdicts": [],
                    "total_claims": 0,
                    "high_validity_count": 0,
                    "medium_validity_count": 0,
                    "low_validity_count": 0,
                    "contradicted_count": 0,
                    "errors": list(state.get("errors", [])),
                }
            }

        # Build importance lookup
        importance_map = {c["id"]: c.get("importance_score", 0.5) for c in approved_claims}

        # Count verdicts
        high_count = sum(1 for v in claim_verdicts if v["verdict"] == "high")
        medium_count = sum(1 for v in claim_verdicts if v["verdict"] == "medium")
        low_count = sum(1 for v in claim_verdicts if v["verdict"] == "low")
        contradicted_count = sum(1 for v in claim_verdicts if v["verdict"] == "contradicted")

        llm = get_llm(complexity="standard")

        # Summarise verdicts for the LLM
        verdicts_summary = json.dumps(
            [
                {
                    "claim": v["claim_text"],
                    "verdict": v["verdict"],
                    "confidence": v["confidence"],
                    "importance_score": importance_map.get(v["claim_id"], 0.5),
                    "supporting_sources": len(v.get("supporting_evidence", [])),
                    "contradicting_sources": len(v.get("contradicting_evidence", [])),
                }
                for v in claim_verdicts
            ],
            indent=2,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Synthesize these per-claim verdicts into an overall assessment:\n\n{verdicts_summary}"
            ),
        ]

        try:
            response = llm.invoke(messages)
            content = response.content.strip()
            parsed = parse_llm_json(content)
            overall_verdict_str = parsed.get("verdict", "mixed")
            summary = parsed.get("summary", "Verification complete.")

        except Exception as e:
            logger.warning(f"[{run_id}] [synthesize] LLM call failed, falling back to heuristic: {e}")
            # Heuristic fallback
            total = len(claim_verdicts)
            if contradicted_count > 0:
                overall_verdict_str = "mixed"
            elif high_count / total >= 0.7:
                overall_verdict_str = "high"
            elif low_count / total >= 0.5:
                overall_verdict_str = "low"
            else:
                overall_verdict_str = "medium"
            summary = (
                f"Verified {total} claim(s): {high_count} high validity, "
                f"{medium_count} medium, {low_count} low, {contradicted_count} contradicted."
            )

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [synthesize] Overall verdict: {overall_verdict_str} in {elapsed:.2f}s"
        )

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "synthesize",
                "status": "completed",
                "detail": f"Overall verdict: {overall_verdict_str.upper()}",
                "data": {"verdict": overall_verdict_str},
            })

        overall_verdict = {
            "summary": summary,
            "verdict": overall_verdict_str,
            "claim_verdicts": claim_verdicts,
            "total_claims": len(claim_verdicts),
            "high_validity_count": high_count,
            "medium_validity_count": medium_count,
            "low_validity_count": low_count,
            "contradicted_count": contradicted_count,
            "errors": list(state.get("errors", [])),
        }

        return {"overall_verdict": overall_verdict}

    except Exception as e:
        logger.exception(f"[{run_id}] [synthesize] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "synthesize",
                "status": "error",
                "detail": f"Synthesis failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"synthesize: {str(e)}")
        return {
            "overall_verdict": None,
            "errors": errors,
        }
