import asyncio
import json
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.models import OverallVerdict, VerifyRequest, VerifyResponse
from backend.agents.callbacks import (
    StreamingCallbackHandler,
    register as register_callback,
    unregister as unregister_callback,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Validity API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory run store
# ---------------------------------------------------------------------------
# Each entry: { run_id, status, queue, result, error }
# Intentionally simple — single-process, no persistence needed for Phase 2.
runs: dict[str, dict] = {}

_SENTINEL = object()  # Signals pipeline completion on the queue


async def _run_pipeline(run_id: str, text: str) -> None:
    """Background task: runs the verification pipeline and pushes events via queue."""
    run = runs.get(run_id)
    if run is None:
        logger.error(f"[{run_id}] run not found in store")
        return

    queue: asyncio.Queue = run["queue"]
    loop = asyncio.get_event_loop()
    cb = StreamingCallbackHandler(queue=queue, run_id=run_id, loop=loop)
    register_callback(run_id, cb)

    try:
        await cb.aemit({
            "type": "pipeline_start",
            "node": "pipeline",
            "status": "running",
            "detail": "Starting verification pipeline...",
        })

        from backend.agents.graph import verification_graph

        initial_state = {
            "input_text": text,
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

        final_state = await verification_graph.ainvoke(initial_state)

        overall = final_state.get("overall_verdict")
        if overall is None:
            raise ValueError("Pipeline completed but produced no verdict")

        verdict = OverallVerdict(**overall) if isinstance(overall, dict) else overall
        verdict_dict = verdict.model_dump()

        runs[run_id]["status"] = "completed"
        runs[run_id]["result"] = verdict_dict

        await cb.aemit({
            "type": "pipeline_complete",
            "node": "pipeline",
            "status": "completed",
            "detail": f"Verification complete — overall verdict: {verdict.verdict.upper()}",
            "data": verdict_dict,
        })

        logger.info(f"[{run_id}] Pipeline complete — verdict: {verdict.verdict}")

    except Exception as exc:
        logger.exception(f"[{run_id}] Pipeline failed")
        runs[run_id]["status"] = "error"
        runs[run_id]["error"] = str(exc)

        await cb.aemit({
            "type": "pipeline_error",
            "node": "pipeline",
            "status": "error",
            "detail": f"Pipeline failed: {str(exc)}",
            "data": {"error": str(exc)},
        })

    finally:
        unregister_callback(run_id)
        # Put a sentinel so any waiting WebSocket consumer can detect EOF
        await queue.put(_SENTINEL)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "search_provider": settings.SEARCH_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
    }


# ---------------------------------------------------------------------------
# POST /api/verify
# ---------------------------------------------------------------------------

@app.post("/api/verify")
async def verify(request: VerifyRequest, sync: bool = False):
    """Start a verification run.

    - Default (async): returns {run_id, status: "running"} immediately.
      Connect to WS /api/verify/{run_id}/stream for live events.
    - ?sync=true: runs synchronously (Phase 1 behaviour) and returns full verdict.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"[{run_id}] Received verify request ({len(request.text)} chars), sync={sync}")

    if sync:
        # --- Phase 1 synchronous fallback ---
        try:
            from backend.agents.graph import verification_graph

            initial_state = {
                "input_text": request.text,
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

            final_state = await verification_graph.ainvoke(initial_state)

            overall = final_state.get("overall_verdict")
            if overall is None:
                return VerifyResponse(
                    run_id=run_id,
                    status="error",
                    error="Pipeline completed but produced no verdict",
                )

            verdict = OverallVerdict(**overall) if isinstance(overall, dict) else overall
            logger.info(f"[{run_id}] Sync verification complete — verdict: {verdict.verdict}")
            return VerifyResponse(run_id=run_id, status="completed", result=verdict)

        except Exception as e:
            logger.exception(f"[{run_id}] Sync verification failed")
            return VerifyResponse(run_id=run_id, status="error", error=str(e))

    # --- Async path: launch background task ---
    queue: asyncio.Queue = asyncio.Queue()
    runs[run_id] = {
        "run_id": run_id,
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
    }

    asyncio.create_task(_run_pipeline(run_id, request.text))

    return {"run_id": run_id, "status": "running"}


# ---------------------------------------------------------------------------
# WS /api/verify/{run_id}/stream
# ---------------------------------------------------------------------------

@app.websocket("/api/verify/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str):
    """Stream verification events to the client over WebSocket.

    - If the run is still executing, events arrive as they fire.
    - If the run is already complete, immediately sends the cached result and closes.
    - If the run_id is unknown, closes with an error.
    """
    await websocket.accept()

    run = runs.get(run_id)
    if run is None:
        await websocket.send_json({
            "type": "pipeline_error",
            "node": "pipeline",
            "status": "error",
            "detail": f"Unknown run_id: {run_id}",
        })
        await websocket.close(code=4004)
        return

    # If already done, send result immediately and close
    if run["status"] == "completed" and run["result"] is not None:
        await websocket.send_json({
            "type": "pipeline_complete",
            "node": "pipeline",
            "status": "completed",
            "detail": "Verification complete (cached result)",
            "data": run["result"],
        })
        await websocket.close()
        return

    if run["status"] == "error":
        await websocket.send_json({
            "type": "pipeline_error",
            "node": "pipeline",
            "status": "error",
            "detail": run.get("error", "Unknown error"),
        })
        await websocket.close()
        return

    # Stream events from the queue
    queue: asyncio.Queue = run["queue"]
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            await websocket.send_json(item)

            # Terminal events — close after sending
            if item.get("type") in ("pipeline_complete", "pipeline_error"):
                break

    except WebSocketDisconnect:
        # Client disconnected — pipeline continues, events are discarded
        logger.info(f"[{run_id}] WebSocket client disconnected mid-stream")
    except Exception as exc:
        logger.warning(f"[{run_id}] WebSocket stream error: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GET /api/verify/{run_id}/result  (poll fallback)
# ---------------------------------------------------------------------------

@app.get("/api/verify/{run_id}/result")
async def get_result(run_id: str):
    """Poll endpoint — returns final verdict or {status: running} if in progress."""
    run = runs.get(run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")

    if run["status"] == "running":
        return {"status": "running", "run_id": run_id}

    if run["status"] == "error":
        return {"status": "error", "run_id": run_id, "error": run["error"]}

    return {"status": "completed", "run_id": run_id, "result": run["result"]}
