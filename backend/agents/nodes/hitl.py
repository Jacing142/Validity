"""
HITL (Human-in-the-Loop) node for Validity Phase 3.

HITL Implementation: Approach B: Manual asyncio.Event
Chosen because: The graph is compiled without a LangGraph checkpointer (graph.compile()
with no MemorySaver), and the pipeline is invoked with ainvoke() in a single call.
Adding a MemorySaver + catching GraphInterrupt + re-invoking with Command(resume=...)
would require significant changes to the working Phase 2 invocation pattern.

Instead, we store an asyncio.Event on the per-run StreamingCallbackHandler. The hitl
node awaits this event. The WebSocket handler sets it when the user sends a
hitl_response message. Since ainvoke() runs in the asyncio event loop and the WebSocket
handler runs concurrently in the same loop, this is textbook asyncio coordination.

Skip mode (sync endpoint, MCP, testing): if no hitl_event is set on the callback
(or no callback exists), the node auto-approves ranked_claims immediately.
"""

import asyncio
import logging
import uuid

from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback

logger = logging.getLogger(__name__)

# If user takes longer than this, auto-approve all ranked claims and continue.
HITL_TIMEOUT_SECONDS = 300  # 5 minutes


async def hitl_node(state: VerificationState) -> dict:
    """Pause the pipeline, emit ranked claims to the user for review, and wait.

    Resumes when the WebSocket handler sets cb.hitl_event (triggered by a
    hitl_response message from the client), or after HITL_TIMEOUT_SECONDS.
    """
    run_id = state.get("run_id", "unknown")
    ranked_claims = state.get("ranked_claims", [])

    cb = get_callback(run_id)

    # --- Skip mode ---
    # No callback (sync endpoint) or no hitl_event configured (MCP / testing).
    if cb is None or cb.hitl_event is None:
        logger.info(f"[{run_id}] [hitl] No hitl_event — skipping HITL (auto-approve all)")
        return {"approved_claims": ranked_claims}

    # --- Emit hitl_request to frontend ---
    await cb.aemit({
        "type": "hitl_request",
        "node": "hitl",
        "status": "waiting",
        "detail": f"Waiting for your review of {len(ranked_claims)} claim{'s' if len(ranked_claims) != 1 else ''}...",
        "data": {"claims": ranked_claims},
    })

    logger.info(f"[{run_id}] [hitl] Paused — awaiting user review of {len(ranked_claims)} claims")

    # --- Wait for user response ---
    try:
        await asyncio.wait_for(cb.hitl_event.wait(), timeout=HITL_TIMEOUT_SECONDS)
        approved_claims = cb.hitl_response.get("approved_claims", ranked_claims)
        logger.info(f"[{run_id}] [hitl] Resumed — user approved {len(approved_claims)} claims")
    except asyncio.TimeoutError:
        logger.warning(
            f"[{run_id}] [hitl] Timed out after {HITL_TIMEOUT_SECONDS}s "
            f"— auto-approving all {len(ranked_claims)} ranked claims"
        )
        approved_claims = ranked_claims
        await cb.aemit({
            "type": "node_event",
            "node": "hitl",
            "status": "completed",
            "detail": "Review timed out — auto-approving all ranked claims and continuing...",
        })

    # --- Validate / normalise approved claims ---
    # The frontend sends back claims with {id, text, importance_score}.
    # Custom claims added in the modal may have client-generated IDs.
    validated = []
    for claim in approved_claims:
        text = str(claim.get("text", "")).strip()
        if not text:
            logger.warning(f"[{run_id}] [hitl] Skipping claim with empty text")
            continue
        if len(text) > 500:
            logger.warning(f"[{run_id}] [hitl] Skipping claim exceeding 500 chars")
            continue
        claim = dict(claim)
        if not claim.get("id"):
            claim["id"] = str(uuid.uuid4())
        if "importance_score" not in claim:
            claim["importance_score"] = 1.0
        validated.append(claim)

    await cb.aemit({
        "type": "node_event",
        "node": "hitl",
        "status": "completed",
        "detail": (
            f"Resuming with {len(validated)} approved claim{'s' if len(validated) != 1 else ''}..."
            if validated
            else "No claims selected — stopping verification."
        ),
    })

    return {"approved_claims": validated}
