"""
Quick WebSocket test — run the server first, then:
  python scripts/test_ws.py

Starts a verification run, connects to the WebSocket stream, and prints each
event as it arrives. Use this to verify the streaming backend before building
the frontend.
"""

import asyncio
import json
import sys

import httpx
import websockets


TEST_TEXT = (
    "The Earth revolves around the Sun. "
    "Water boils at 100 degrees Celsius at sea level. "
    "The Great Wall of China is visible from space."
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

    # 2. Connect to WebSocket and print events
    uri = f"{WS_BASE}/api/verify/{run_id}/stream"
    try:
        async with websockets.connect(uri, ping_timeout=120, close_timeout=30) as ws:
            async for message in ws:
                event = json.loads(message)
                ev_type = event.get("type", "")
                node = event.get("node", "system")
                status = event.get("status", "")
                detail = event.get("detail", "")

                # Format output
                status_icon = {
                    "running": "⟳",
                    "completed": "✓",
                    "error": "✗",
                }.get(status, "·")

                print(f"  {status_icon} [{node:<12}] {detail}")

                if ev_type in ("pipeline_complete", "pipeline_error"):
                    if ev_type == "pipeline_complete":
                        result = event.get("data", {})
                        verdict = result.get("verdict", "?").upper()
                        total = result.get("total_claims", 0)
                        print(f"\n{'='*60}")
                        print(f"  OVERALL VERDICT: {verdict}")
                        print(f"  Claims verified: {total}")
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
