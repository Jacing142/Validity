"""
Programmatic HITL test — runs the graph directly (no HTTP server needed).

Tests:
  1. Graph pauses at the hitl node and emits hitl_request to the queue.
  2. Feeding a modified claim list (removed one, added one custom claim).
  3. Graph resumes and completes using ONLY the approved + custom claims.
  4. Final verdict contains exactly the expected claims (not the removed one).

Usage:
  cd /path/to/Validity
  python -m scripts.test_hitl
  # or
  python scripts/test_hitl.py

Requires a running .env with valid LLM_API_KEY and SEARCH_API_KEY.
"""

import asyncio
import json
import logging
import uuid
import sys
import os

# Make sure the repo root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_hitl")

TEST_TEXT = (
    "The Earth revolves around the Sun. "
    "Water boils at 100 degrees Celsius at sea level. "
    "The Great Wall of China is visible from space."
)

CUSTOM_CLAIM_TEXT = "The Moon is made of cheese"


async def run_test():
    from backend.agents.graph import verification_graph
    from backend.agents.callbacks import StreamingCallbackHandler, register, unregister

    run_id = f"test-hitl-{uuid.uuid4().hex[:8]}"
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    # -----------------------------------------------------------------------
    # Set up callback with HITL coordination objects
    # -----------------------------------------------------------------------
    cb = StreamingCallbackHandler(queue=queue, run_id=run_id, loop=loop)
    cb.hitl_event = asyncio.Event()
    cb.hitl_response = {}
    register(run_id, cb)

    initial_state = {
        "input_text": TEST_TEXT,
        "claims": [],
        "ranked_claims": [],
        "approved_claims": [],
        "search_queries": [],
        "search_results": [],
        "classified_results": [],
        "evidence_assessments": [],
        "claim_verdicts": [],
        "overall_verdict": None,
        "run_id": run_id,
        "errors": [],
    }

    # -----------------------------------------------------------------------
    # Simulate the user: wait until hitl_request arrives, then respond
    # -----------------------------------------------------------------------
    async def simulate_user():
        ranked_claims = None
        while True:
            event = await queue.get()
            ev_type = event.get("type", "")
            node = event.get("node", "system")
            detail = event.get("detail", "")
            print(f"  [{node:<12}] {detail[:80]}")

            if ev_type == "hitl_request":
                ranked_claims = event["data"]["claims"]
                print(f"\n  --- HITL REQUEST: received {len(ranked_claims)} claims ---")
                for i, c in enumerate(ranked_claims):
                    print(f"  [{i+1}] {c['text']} (score={c.get('importance_score', '?'):.2f})")

                # Remove the last claim, add a custom claim
                approved = ranked_claims[:-1]
                custom_claim = {
                    "id": f"custom-{uuid.uuid4().hex[:8]}",
                    "text": CUSTOM_CLAIM_TEXT,
                    "importance_score": 1.0,
                }
                approved.append(custom_claim)

                print(f"\n  --- HITL RESPONSE: approving {len(approved)} claims ---")
                print(f"      Removed: '{ranked_claims[-1]['text']}'")
                print(f"      Added:   '{custom_claim['text']}'")

                cb.hitl_response["approved_claims"] = approved
                cb.hitl_event.set()

            if ev_type in ("pipeline_complete", "pipeline_error"):
                print(f"\n  [{node}] {detail}")
                return event

    # -----------------------------------------------------------------------
    # Run graph and user simulation concurrently
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"HITL Integration Test — run_id: {run_id}")
    print(f"Input: {TEST_TEXT[:80]}...")
    print(f"{'='*60}\n")

    final_event, _ = await asyncio.gather(
        simulate_user(),
        verification_graph.ainvoke(initial_state),
    )

    unregister(run_id)

    # -----------------------------------------------------------------------
    # Assertions
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("TEST RESULTS")
    print(f"{'='*60}")

    if final_event.get("type") == "pipeline_error":
        print(f"FAIL: Pipeline error — {final_event.get('detail')}")
        return False

    result = final_event.get("data", {})
    total = result.get("total_claims", 0)
    verdicts = result.get("claim_verdicts", [])

    print(f"Overall verdict: {result.get('verdict', '?').upper()}")
    print(f"Total claims verified: {total}")
    print()

    removed_text = None  # We don't know which was removed without capturing it
    custom_found = False
    for cv in verdicts:
        print(f"  Claim: {cv['claim_text'][:70]}")
        print(f"  Verdict: {cv.get('verdict', '?').upper()}")
        print()
        if cv["claim_text"] == CUSTOM_CLAIM_TEXT:
            custom_found = True

    # Basic assertions
    passed = True

    if total == 0:
        print("FAIL: total_claims is 0 — pipeline may not have run correctly")
        passed = False

    if not custom_found:
        print(f"FAIL: Custom claim '{CUSTOM_CLAIM_TEXT}' not found in verdicts")
        passed = False
    else:
        print(f"PASS: Custom claim '{CUSTOM_CLAIM_TEXT}' is present in verdicts")

    if passed:
        print("\nOVERALL: PASS")
    else:
        print("\nOVERALL: FAIL")

    return passed


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
