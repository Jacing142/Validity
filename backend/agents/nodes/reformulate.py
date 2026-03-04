"""
Reformulate node — generates alternative wordings for subjective claims.
Sits between decompose and rank in the graph.

For verifiable claims: passes through unchanged.
For subjective claims: generates 2 alternatives:
  1. A cleaner/clearer version of the original statement
  2. A more specific/quantifiable version that could be web-searched
"""

import asyncio
import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a claim reformulation assistant. You receive subjective or opinion-based claims and generate two alternative wordings that are more verifiable.

For each claim, generate exactly two alternatives:
1. **cleaner**: A clearer, less ambiguous version of the same statement. Keep the intent but remove vague language.
2. **quantifiable**: A specific, measurable version that could be verified with a web search. Replace superlatives with rankings, replace "best" with a measurable metric, replace vague quantities with searchable assertions.

Examples:

Claim: "Pizza is the best food in America"
→ cleaner: "Pizza is the most popular food in America"
→ quantifiable: "Pizza is the most consumed food in America by sales revenue"

Claim: "This company has amazing customer service"
→ cleaner: "This company is known for strong customer service"
→ quantifiable: "This company has a customer satisfaction score above the industry average"

Claim: "The Eiffel Tower is one of the most beautiful structures ever built"
→ cleaner: "The Eiffel Tower is widely considered an iconic structure"
→ quantifiable: "The Eiffel Tower is among the most-photographed landmarks in the world"

Return a JSON object with this exact structure:
{
  "reformulations": [
    {
      "id": "<claim id>",
      "cleaner": "Cleaner version of the claim",
      "quantifiable": "Specific, measurable version of the claim"
    },
    ...
  ]
}

Return ONLY the JSON object, no other text."""


async def reformulate_node(state: VerificationState) -> dict:
    """Generate alternative wordings for subjective claims. Verifiable claims pass through unchanged."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [reformulate] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        await cb.aemit({
            "type": "node_event",
            "node": "reformulate",
            "status": "running",
            "detail": "Analyzing claims and generating alternatives for subjective statements...",
        })

    try:
        claims = state.get("claims", [])
        if not claims:
            logger.warning(f"[{run_id}] [reformulate] No claims to process")
            return {"claims": []}

        # Separate subjective claims that need reformulation
        subjective_claims = [c for c in claims if c.get("claim_type") == "subjective"]
        verifiable_claims = [c for c in claims if c.get("claim_type") != "subjective"]

        # Emit events for verifiable claims passing through
        if cb:
            for claim in verifiable_claims:
                await cb.aemit({
                    "type": "node_event",
                    "node": "reformulate",
                    "status": "running",
                    "detail": f"Verifiable — passing through: \"{claim['text'][:70]}\"",
                    "data": {"claim_id": claim["id"], "claim_type": "verifiable"},
                })

        reformulations_map = {}

        if subjective_claims:
            if cb:
                await cb.aemit({
                    "type": "node_event",
                    "node": "reformulate",
                    "status": "running",
                    "detail": f"Generating alternatives for {len(subjective_claims)} subjective claim{'s' if len(subjective_claims) != 1 else ''}...",
                })

            llm = get_llm(complexity="standard")

            claims_text = json.dumps(
                [{"id": c["id"], "text": c["text"]} for c in subjective_claims],
                indent=2,
            )

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=f"Generate two alternative wordings for each of these subjective claims:\n\n{claims_text}"
                ),
            ]

            response = await llm.ainvoke(messages)
            parsed = parse_llm_json(response.content)

            for item in parsed.get("reformulations", []):
                reformulations_map[item["id"]] = {
                    "cleaner": item.get("cleaner", ""),
                    "quantifiable": item.get("quantifiable", ""),
                }

        # Build updated claims list, preserving original order
        updated_claims = []
        for claim in claims:
            claim_copy = dict(claim)
            if claim_copy.get("claim_type") == "subjective" and claim_copy["id"] in reformulations_map:
                ref = reformulations_map[claim_copy["id"]]
                claim_copy["reformulation_options"] = [
                    ref["cleaner"],
                    ref["quantifiable"],
                ]

                if cb:
                    cleaner_preview = ref["cleaner"][:50]
                    quant_preview = ref["quantifiable"][:50]
                    await cb.aemit({
                        "type": "node_event",
                        "node": "reformulate",
                        "status": "running",
                        "detail": (
                            f"Subjective: \"{claim['text'][:50]}...\"\n"
                            f"  → Option 1: \"{cleaner_preview}...\"\n"
                            f"  → Option 2: \"{quant_preview}...\""
                        ),
                        "data": {
                            "claim_id": claim["id"],
                            "claim_type": "subjective",
                            "original": claim["text"],
                            "options": claim_copy["reformulation_options"],
                        },
                    })
            else:
                # Verifiable or failed reformulation — ensure field exists
                claim_copy.setdefault("reformulation_options", [])

            updated_claims.append(claim_copy)

        elapsed = time.time() - start
        logger.info(
            f"[{run_id}] [reformulate] Processed {len(updated_claims)} claims "
            f"({len(verifiable_claims)} verifiable, {len(subjective_claims)} subjective) "
            f"in {elapsed:.2f}s"
        )

        if cb:
            await cb.aemit({
                "type": "node_event",
                "node": "reformulate",
                "status": "completed",
                "detail": (
                    f"Processed {len(updated_claims)} claims: "
                    f"{len(verifiable_claims)} verifiable (unchanged), "
                    f"{len(subjective_claims)} subjective (alternatives generated)"
                ),
                "data": {
                    "verifiable": len(verifiable_claims),
                    "subjective": len(subjective_claims),
                },
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
        # On failure, pass claims through unchanged — ensures pipeline continues
        return {"claims": state.get("claims", []), "errors": errors}
