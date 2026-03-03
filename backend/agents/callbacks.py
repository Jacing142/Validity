"""
Streaming callback handler for Validity Phase 2.

Each node emits structured events to a per-run asyncio.Queue.
The WebSocket endpoint reads from this queue and pushes events to the client.

Usage:
    from backend.agents.callbacks import StreamingCallbackHandler, register, get, unregister

    # In the WebSocket/API layer:
    handler = StreamingCallbackHandler(queue=asyncio.Queue(), run_id=run_id, loop=loop)
    register(run_id, handler)

    # In each node:
    from backend.agents.callbacks import get as get_callback
    cb = get_callback(run_id)
    if cb:
        cb.emit({"type": "node_event", "node": "decompose", "status": "running", "detail": "..."})
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Global registry: run_id -> StreamingCallbackHandler
# Thread-safe reads/writes are GIL-protected for simple dict ops.
_run_callbacks: dict[str, "StreamingCallbackHandler"] = {}


class StreamingCallbackHandler:
    """Captures node events and forwards them to a per-run asyncio.Queue.

    The emit() method is thread-safe and can be called from sync nodes
    running in a ThreadPoolExecutor (LangGraph's default for sync node functions).

    Phase 3 HITL coordination:
        hitl_event    — asyncio.Event set by the WebSocket handler when user responds.
                        None means HITL is disabled (sync endpoint / MCP / testing).
        hitl_response — dict populated by WebSocket handler before setting hitl_event.
                        The hitl node reads hitl_response["approved_claims"] after waking.
    """

    def __init__(self, queue: asyncio.Queue, run_id: str, loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.run_id = run_id
        self._loop = loop
        # HITL coordination — populated by _run_pipeline for async (WebSocket) runs
        self.hitl_event: asyncio.Event | None = None
        self.hitl_response: dict = {}

    def _make_event(self, event: dict) -> dict:
        event = dict(event)
        event.setdefault("run_id", self.run_id)
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return event

    def emit(self, event: dict) -> None:
        """Thread-safe emit — safe to call from sync node functions in thread executors."""
        ev = self._make_event(event)
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(ev), self._loop)
        except Exception as exc:
            logger.warning(f"[{self.run_id}] callback.emit failed: {exc}")

    async def aemit(self, event: dict) -> None:
        """Async emit — use this from async node functions."""
        ev = self._make_event(event)
        await self.queue.put(ev)


def register(run_id: str, handler: StreamingCallbackHandler) -> None:
    """Register a callback handler for the given run_id."""
    _run_callbacks[run_id] = handler


def get(run_id: str) -> Optional[StreamingCallbackHandler]:
    """Retrieve the callback handler for the given run_id, or None."""
    return _run_callbacks.get(run_id)


def unregister(run_id: str) -> None:
    """Remove the callback handler for the given run_id (call after pipeline completes)."""
    _run_callbacks.pop(run_id, None)
