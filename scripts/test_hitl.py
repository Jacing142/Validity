"""
Programmatic HITL test — runs the graph directly (no HTTP server needed).

Tests:
  1. Graph pauses at the hitl node and emits hitl_request to the queue.
  2. Feeding a modified claim list (removed one, added one custom claim).
  3. Graph resumes and completes using ONLY the approved + custom claims.
  4. Final verdict contains exactly the expected claims (not the removed one).

Usage:
  cd /path/to/Validity
  LLM_PROVIDER=mock SEARCH_PROVIDER=mock python scripts/test_hitl.py

Requires a running .env with valid LLM_API_KEY and SEARCH_API_KEY,
OR set LLM_PROVIDER=mock SEARCH_PROVIDER=mock for offline testing.
"""

import asyncio
import logging
import uuid
import sys
import os

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

    # Set up callback with HITL coordination objects
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

    print(f"\n{'='*60}")
    print(f"HITL Integration Test — run_id: {run_id}")
    print(f"Input: {TEST_TEXT[:80]}...")
    print(f"{'='*60}\n")

    removed_claim_text = None

    async def monitor_queue(stop_event: asyncio.Event):
        """Drain the event queue, print events, handle HITL request."""
        nonlocal removed_claim_text
        while not stop_event.is_set():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue

            ev_type = event.get("type", "")
            node = event.get("node", "system")
            detail = event.get("detail", "")
            print(f"  [{node:<12}] {detail[:80]}")

            if ev_type == "hitl_request":
                ranked_claims = event["data"]["claims"]
                print(f"\n  --- HITL REQUEST: received {len(ranked_claims)} claims ---")
                for i, c in enumerate(ranked_claims):
                    print(f"  [{i+1}] {c['text']} (score={c.get('importance_score', '?')})")

                # Remove the last claim, add a custom claim
                removed_claim_text = ranked_claims[-1]["text"] if ranked_claims else None
                approved = ranked_claims[:-1]
                custom_claim = {
                    "id": f"custom-{uuid.uuid4().hex[:8]}",
                    "text": CUSTOM_CLAIM_TEXT,
                    "importance_score": 1.0,
                }
                approved.append(custom_claim)

                print(f"\n  --- HITL RESPONSE: approving {len(approved)} claims ---")
                if removed_claim_text:
                    print(f"      Removed: '{removed_claim_text}'")
                print(f"      Added:   '{custom_claim['text']}'")

                cb.hitl_response["approved_claims"] = approved
                cb.hitl_event.set()
                print()

    # Run graph and queue monitor concurrently
    stop_monitor = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_queue(stop_monitor))

    try:
        final_state = await verification_graph.ainvoke(initial_state)
    finally:
        stop_monitor.set()
        await monitor_task

    unregister(run_id)

    # Assertions on final_state
    print(f"\n{'='*60}")
    print("TEST RESULTS")
    print(f"{'='*60}")

    overall = final_state.get("overall_verdict")
    if overall is None:
        print("FAIL: overall_verdict is None — pipeline did not complete")
        return False

    verdicts = overall.get("claim_verdicts", [])
    total = overall.get("total_claims", 0)
    claim_texts = [cv["claim_text"] for cv in verdicts]

    print(f"Overall verdict: {overall.get('verdict', '?').upper()}")
    print(f"Total claims verified: {total}")
    print()

    for cv in verdicts:
        print(f"  Claim: {cv['claim_text'][:70]}")
        print(f"  Verdict: {cv.get('verdict', '?').upper()}")
        print()

    passed = True

    if CUSTOM_CLAIM_TEXT in claim_texts:
        print(f"PASS: Custom claim '{CUSTOM_CLAIM_TEXT}' is in verdicts")
    else:
        print(f"FAIL: Custom claim '{CUSTOM_CLAIM_TEXT}' NOT found in verdicts")
        passed = False

    if removed_claim_text and removed_claim_text in claim_texts:
        print(f"FAIL: Removed claim '{removed_claim_text[:60]}' is still in verdicts!")
        passed = False
    elif removed_claim_text:
        print(f"PASS: Removed claim '{removed_claim_text[:60]}' is correctly excluded")

    if total > 0:
        print(f"PASS: {total} claims verified (pipeline ran to completion)")
    else:
        print("FAIL: total_claims is 0")
        passed = False

    print(f"\nOVERALL: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
