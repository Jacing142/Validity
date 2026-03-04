import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an adversarial search query generator. For each claim provided, generate search queries designed to find both supporting AND contradicting evidence.

For each claim generate:
- 2-3 AFFIRM queries: designed to find evidence that SUPPORTS the claim
- 2-3 REFUTE queries: designed to find evidence that CONTRADICTS or challenges the claim

Refute queries are critical — actively trying to disprove a claim is what makes verification meaningful.

Example for claim "The Great Wall of China is visible from space":
- AFFIRM: "Great Wall China visible from space", "structures visible from low Earth orbit"
- REFUTE: "Great Wall China NOT visible from space myth", "astronauts cannot see Great Wall from orbit"

Return a JSON object with this exact structure:
{
  "queries": [
    {
      "claim_id": "<claim id>",
      "intent": "affirm",
      "query": "search query text"
    },
    {
      "claim_id": "<claim id>",
      "intent": "refute",
      "query": "search query text"
    },
    ...
  ]
}

Return ONLY the JSON object, no other text."""


def query_gen_node(state: VerificationState) -> dict:
    """Node 3: Generate adversarial affirm + refute search queries per claim."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [query_gen] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    try:
        approved_claims = state.get("approved_claims", [])
        if not approved_claims:
            logger.warning(f"[{run_id}] [query_gen] No approved claims to generate queries for")
            return {"search_queries": []}

        if cb:
            for claim in approved_claims:
                claim_preview = claim["text"][:80] + "..." if len(claim["text"]) > 80 else claim["text"]
                cb.emit({
                    "type": "node_event",
                    "node": "query_gen",
                    "status": "running",
                    "detail": f"Generating search queries for: \"{claim_preview}\"",
                    "data": {"claim_id": claim["id"]},
                })

        llm = get_llm(complexity="standard")

        claims_text = json.dumps(
            [{"id": c["id"], "text": c["text"]} for c in approved_claims],
            indent=2,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Generate affirm and refute search queries for each of these claims:\n\n{claims_text}"
            ),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        parsed = parse_llm_json(content)
        queries = parsed.get("queries", [])

        elapsed = time.time() - start
        affirm_count = sum(1 for q in queries if q.get("intent") == "affirm")
        refute_count = sum(1 for q in queries if q.get("intent") == "refute")
        num_claims = len(approved_claims)
        logger.info(
            f"[{run_id}] [query_gen] Generated {len(queries)} queries "
            f"({affirm_count} affirm, {refute_count} refute) in {elapsed:.2f}s"
        )

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "query_gen",
                "status": "completed",
                "detail": f"Generated {affirm_count} affirm + {refute_count} refute queries for {num_claims} claim{'s' if num_claims != 1 else ''}",
                "data": {"total": len(queries), "affirm": affirm_count, "refute": refute_count},
            })

        return {"search_queries": queries}

    except Exception as e:
        logger.exception(f"[{run_id}] [query_gen] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "query_gen",
                "status": "error",
                "detail": f"Query generation failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"query_gen: {str(e)}")
        return {"search_queries": [], "errors": errors}
