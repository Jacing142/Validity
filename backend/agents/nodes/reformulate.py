"""
Reformulate node — classifies claims and suggests quantifiable alternatives for subjective ones.
Sits between decompose and rank in the graph.
"""
import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a claim classification and reformulation assistant. For each claim, determine if it is directly verifiable or if it is subjective/abstract.

Definitions:
- **verifiable**: The claim contains a specific, checkable factual assertion. It could be confirmed or denied using evidence from public sources. Examples: statistics, dates, measurements, named events, rankings from official sources.
- **subjective**: The claim contains opinion, superlative language ("best", "worst", "amazing"), vague assertions ("many people think"), or abstract statements that cannot be directly checked against a source.

For subjective claims, suggest a quantifiable reformulation — a closely related claim that IS verifiable and captures the likely intent of the original statement.

Reformulation guidelines:
- Preserve the original meaning as closely as possible
- Replace superlatives with measurable metrics (e.g., "best" → "highest-rated", "most popular" → "highest sales figures")
- Replace vague quantities with specific, searchable assertions
- The reformulation should be something a web search could actually verify

Return a JSON object with this exact structure:
{
  "classifications": [
    {
      "id": "<claim id>",
      "classification": "verifiable" | "subjective",
      "reasoning": "One-sentence explanation of classification",
      "reformulation": "Suggested quantifiable reformulation (only if subjective, null if verifiable)"
    },
    ...
  ]
}

Return ONLY the JSON object, no other text."""


async def reformulate_node(state: VerificationState) -> dict:
    """Classify claims as verifiable or subjective and suggest reformulations."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [reformulate] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        await cb.aemit({
            "type": "node_event",
            "node": "reformulate",
            "status": "running",
            "detail": "Classifying claims and suggesting reformulations for subjective statements...",
        })

    try:
        claims = state.get("claims", [])
        if not claims:
            logger.warning(f"[{run_id}] [reformulate] No claims to classify")
            return {"claims": []}

        llm = get_llm(complexity="standard")

        claims_text = json.dumps(
            [{"id": c["id"], "text": c["text"]} for c in claims],
            indent=2,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Classify each claim and suggest reformulations where needed:\n\n{claims_text}"),
        ]

        response = await llm.ainvoke(messages)
        content = response.content.strip()
        parsed = parse_llm_json(content)

        classifications = {
            item["id"]: item for item in parsed.get("classifications", [])
        }

        # Annotate claims with classification and reformulation
        updated_claims = []
        for claim in claims:
            claim_copy = dict(claim)
            classification = classifications.get(claim["id"], {})
            claim_copy["classification"] = classification.get("classification", "verifiable")
            claim_copy["reformulation"] = classification.get("reformulation", None)
            claim_copy["reformulation_reasoning"] = classification.get("reasoning", "")
            # Keep original text in a separate field for the HITL modal
            claim_copy["original_text"] = claim["text"]
            updated_claims.append(claim_copy)

            if cb:
                if claim_copy["classification"] == "subjective" and claim_copy["reformulation"]:
                    await cb.aemit({
                        "type": "node_event",
                        "node": "reformulate",
                        "status": "running",
                        "detail": f"Subjective: \"{claim['text'][:60]}...\" → suggested: \"{claim_copy['reformulation'][:60]}...\"",
                        "data": {
                            "claim_id": claim["id"],
                            "classification": "subjective",
                            "original": claim["text"],
                            "reformulation": claim_copy["reformulation"],
                        },
                    })
                else:
                    await cb.aemit({
                        "type": "node_event",
                        "node": "reformulate",
                        "status": "running",
                        "detail": f"Verifiable: \"{claim['text'][:80]}\"",
                        "data": {
                            "claim_id": claim["id"],
                            "classification": "verifiable",
                        },
                    })

        subjective_count = sum(1 for c in updated_claims if c["classification"] == "subjective")
        verifiable_count = len(updated_claims) - subjective_count

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [reformulate] Classified {len(updated_claims)} claims "
            f"({verifiable_count} verifiable, {subjective_count} subjective) in {elapsed:.2f}s"
        )

        if cb:
            await cb.aemit({
                "type": "node_event",
                "node": "reformulate",
                "status": "completed",
                "detail": f"Classified {len(updated_claims)} claims: {verifiable_count} verifiable, {subjective_count} need reformulation",
                "data": {"verifiable": verifiable_count, "subjective": subjective_count},
            })

        return {"claims": updated_claims}

    except Exception as e:
        logger.exception(f"[{run_id}] [reformulate] Failed")
        if cb:
            await cb.aemit({
                "type": "node_event",
                "node": "reformulate",
                "status": "error",
                "detail": f"Reformulation failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"reformulate: {str(e)}")
        # On failure, pass claims through unchanged (all treated as verifiable)
        return {"claims": state.get("claims", []), "errors": errors}
