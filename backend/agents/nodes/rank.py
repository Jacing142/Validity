import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm, settings
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a claim ranking assistant. Given a list of atomic claims, score each one on two dimensions:

1. **Verifiability** (0.0–1.0): How easily can this claim be verified with web searches and public sources?
   - 1.0 = clearly verifiable with objective data (scientific facts, statistics, historical events)
   - 0.5 = verifiable but requires interpretation
   - 0.0 = essentially unverifiable (opinions disguised as facts, vague claims)

2. **Importance** (0.0–1.0): How significant is this claim to the overall meaning of the text?
   - 1.0 = central claim that the text depends on
   - 0.5 = supporting detail
   - 0.0 = trivial or incidental

The combined score is the average of verifiability and importance.

Return a JSON object with this exact structure:
{
  "scored_claims": [
    {
      "id": "<claim id>",
      "verifiability": 0.9,
      "importance": 0.8,
      "combined_score": 0.85
    },
    ...
  ]
}

Return ONLY the JSON object, no other text."""


def rank_node(state: VerificationState) -> dict:
    """Node 2: Score and rank claims by verifiability and importance, select top N."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [rank] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        cb.emit({
            "type": "node_event",
            "node": "rank",
            "status": "running",
            "detail": "Ranking claims by verifiability and importance...",
        })

    try:
        claims = state.get("claims", [])
        if not claims:
            logger.warning(f"[{run_id}] [rank] No claims to rank")
            return {"ranked_claims": [], "approved_claims": []}

        llm = get_llm(complexity="standard")

        claims_text = json.dumps(
            [{"id": c["id"], "text": c["text"]} for c in claims],
            indent=2,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Score and rank these claims:\n\n{claims_text}"),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)
        scored = {item["id"]: item["combined_score"] for item in parsed.get("scored_claims", [])}

        # Apply scores to claims
        scored_claims = []
        for claim in claims:
            claim_copy = dict(claim)
            claim_copy["importance_score"] = scored.get(claim["id"], 0.5)
            scored_claims.append(claim_copy)

        # Sort descending by importance_score, take top MAX_CLAIMS
        scored_claims.sort(key=lambda c: c["importance_score"], reverse=True)
        top_claims = scored_claims[: settings.MAX_CLAIMS]

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [rank] Ranked {len(claims)} claims, selected top {len(top_claims)} in {elapsed:.2f}s"
        )

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "rank",
                "status": "completed",
                "detail": f"Selected top {len(top_claims)} claim{'s' if len(top_claims) != 1 else ''} for verification",
                "data": {"selected": [c["text"] for c in top_claims]},
            })

        # Phase 3: approved_claims is set by the hitl node (not here).
        return {"ranked_claims": top_claims}

    except Exception as e:
        logger.exception(f"[{run_id}] [rank] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "rank",
                "status": "error",
                "detail": f"Ranking failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"rank: {str(e)}")
        # Fall back to original order, capped at MAX_CLAIMS
        fallback = state.get("claims", [])[: settings.MAX_CLAIMS]
        return {"ranked_claims": fallback, "errors": errors}
