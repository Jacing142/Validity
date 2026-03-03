"""
WebSocket test — run the server first, then:
  python scripts/test_ws.py

Phase 3: Tests the full HITL flow over WebSocket.
  1. Starts a verification run.
  2. Connects to the WebSocket stream.
  3. When hitl_request arrives, removes the last claim and adds a custom claim.
  4. Sends hitl_response back over the same WebSocket.
  5. Verifies the pipeline resumes and produces results for only the approved claims.

Usage:
  uvicorn backend.main:app --reload   # in one terminal
  python scripts/test_ws.py           # in another terminal
"""

import asyncio
import json
import sys
import uuid

import httpx
import websockets


TEST_TEXT = (
    "The Earth revolves around the Sun. "
    "Water boils at 100 degrees Celsius at sea level. "
    "The Great Wall of China is visible from space. "
    "The speed of light is approximately 300,000 km per second. "
    "Humans use only 10% of their brain."
)

BASE_URL = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


async def test():
    # 1. Start a verification run
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/api/verify",
            json={"text": TEST_TEXT},
        )
        resp.raise_for_status()
        data = resp.json()
        run_id = data["run_id"]
        print(f"\n✓ Run started: {run_id}")
        print(f"  Connecting to WebSocket stream...\n")

    # 2. Connect to WebSocket and handle the HITL flow
    uri = f"{WS_BASE}/api/verify/{run_id}/stream"
    hitl_responded = False
    removed_claim_text = None

    try:
        async with websockets.connect(uri, ping_timeout=300, close_timeout=30) as ws:
            async for message in ws:
                event = json.loads(message)
                ev_type = event.get("type", "")
                node = event.get("node", "system")
                status = event.get("status", "")
                detail = event.get("detail", "")

                status_icon = {
                    "running": "⟳",
                    "completed": "✓",
                    "error": "✗",
                    "waiting": "…",
                }.get(status, "·")

                print(f"  {status_icon} [{node:<12}] {detail[:80]}")

                # 3. When HITL request arrives, respond
                if ev_type == "hitl_request" and not hitl_responded:
                    claims = event["data"]["claims"]
                    print(f"\n  {'─'*50}")
                    print(f"  HITL: Received {len(claims)} ranked claims:")
                    for i, c in enumerate(claims):
                        print(f"    [{i+1}] {c['text'][:60]} (score={c.get('importance_score', 0):.2f})")

                    # Remove the last claim, add a custom claim
                    removed_claim_text = claims[-1]["text"] if claims else None
                    approved = claims[:-1]
                    custom_claim = {
                        "id": f"custom-{uuid.uuid4().hex[:8]}",
                        "text": "The Moon landing in 1969 was real",
                        "importance_score": 1.0,
                    }
                    approved.append(custom_claim)

                    print(f"\n  HITL: Approving {len(approved)} claims:")
                    if removed_claim_text:
                        print(f"    ✗ Removed: '{removed_claim_text[:60]}'")
                    print(f"    + Added:   '{custom_claim['text']}'")
                    print(f"  {'─'*50}\n")

                    await ws.send(json.dumps({
                        "type": "hitl_response",
                        "approved_claims": approved,
                    }))
                    hitl_responded = True

                if ev_type in ("pipeline_complete", "pipeline_error"):
                    if ev_type == "pipeline_complete":
                        result = event.get("data", {})
                        verdict = result.get("verdict", "?").upper()
                        total = result.get("total_claims", 0)
                        print(f"\n{'='*60}")
                        print(f"  OVERALL VERDICT: {verdict}")
                        print(f"  Claims verified: {total}")
                        print()

                        claim_verdicts = result.get("claim_verdicts", [])
                        for cv in claim_verdicts:
                            print(f"  • {cv['claim_text'][:60]}")
                            print(f"    → {cv.get('verdict', '?').upper()}")

                        # Verify removed claim is NOT in results
                        if removed_claim_text:
                            texts = [cv["claim_text"] for cv in claim_verdicts]
                            if removed_claim_text in texts:
                                print(f"\n  FAIL: Removed claim still in results!")
                            else:
                                print(f"\n  PASS: Removed claim correctly excluded from results.")

                        # Verify custom claim IS in results
                        custom_texts = [cv["claim_text"] for cv in claim_verdicts]
                        if "The Moon landing in 1969 was real" in custom_texts:
                            print(f"  PASS: Custom claim is present in results.")
                        else:
                            print(f"  FAIL: Custom claim missing from results!")

                        print(f"{'='*60}\n")
                    else:
                        print(f"\n  PIPELINE ERROR: {detail}\n")
                    break

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as exc:
        print(f"\nWebSocket error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test())
