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
    get as get_callback,
    unregister as unregister_callback,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Validity API", version="3.0.0")

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
# Intentionally simple — single-process, no persistence needed for Phase 3.
runs: dict[str, dict] = {}

_SENTINEL = object()  # Signals pipeline completion on the queue


async def _run_pipeline(run_id: str, text: str, enable_hitl: bool = True) -> None:
    """Background task: runs the verification pipeline and pushes events via queue.

    Args:
        run_id:      Unique identifier for this run.
        text:        Input text to verify.
        enable_hitl: When True (async/WebSocket path), creates an asyncio.Event
                     on the callback so the hitl node can pause and wait for user
                     input. When False (sync endpoint), HITL is skipped.
    """
    run = runs.get(run_id)
    if run is None:
        logger.error(f"[{run_id}] run not found in store")
        return

    queue: asyncio.Queue = run["queue"]
    loop = asyncio.get_event_loop()
    cb = StreamingCallbackHandler(queue=queue, run_id=run_id, loop=loop)

    if enable_hitl:
        # Phase 3: attach HITL coordination objects to the callback.
        # The hitl node reads cb.hitl_event; the WebSocket handler sets it.
        cb.hitl_event = asyncio.Event()
        cb.hitl_response = {}

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

        # Build a meaningful detail message for the no-claims case
        if verdict.total_claims == 0:
            detail = "No claims were selected for verification."
        else:
            detail = f"Verification complete — overall verdict: {verdict.verdict.upper()}"

        await cb.aemit({
            "type": "pipeline_complete",
            "node": "pipeline",
            "status": "completed",
            "detail": detail,
            "data": verdict_dict,
        })

        logger.info(f"[{run_id}] Pipeline complete — verdict: {verdict.verdict} ({verdict.total_claims} claims)")

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
      HITL is automatically skipped in sync mode — approved_claims = ranked_claims.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"[{run_id}] Received verify request ({len(request.text)} chars), sync={sync}")

    if sync:
        # --- Phase 1 synchronous fallback — no HITL ---
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

            # No callback registered → hitl_node sees cb=None → auto-approves
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

    # --- Async path: launch background task with HITL enabled ---
    queue: asyncio.Queue = asyncio.Queue()
    runs[run_id] = {
        "run_id": run_id,
        "status": "running",
        "queue": queue,
        "result": None,
        "error": None,
    }

    asyncio.create_task(_run_pipeline(run_id, request.text, enable_hitl=True))

    return {"run_id": run_id, "status": "running"}


# ---------------------------------------------------------------------------
# WS /api/verify/{run_id}/stream  (Phase 3: bidirectional)
# ---------------------------------------------------------------------------

@app.websocket("/api/verify/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str):
    """Bidirectional WebSocket for verification event streaming and HITL responses.

    Server → Client: node events, hitl_request, pipeline_complete / pipeline_error
    Client → Server: hitl_response { type, approved_claims }

    Phase 3 flow:
        1. Events stream for decompose and rank nodes.
        2. Server sends hitl_request with ranked claims.
        3. Client shows modal, user reviews, client sends hitl_response.
        4. Server wakes up hitl node, pipeline resumes.
        5. Events stream for remaining nodes.
        6. Server sends pipeline_complete.
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

    # --- Bidirectional streaming ---
    queue: asyncio.Queue = run["queue"]

    async def send_events() -> None:
        """Read events from the pipeline queue and send them to the client."""
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                return
            await websocket.send_json(item)
            if item.get("type") in ("pipeline_complete", "pipeline_error"):
                return

    async def receive_messages() -> None:
        """Listen for incoming client messages (primarily hitl_response)."""
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"[{run_id}] WebSocket client disconnected")
                # If pipeline is paused at HITL, it will auto-approve after timeout.
                return
            except Exception as exc:
                logger.warning(f"[{run_id}] WebSocket receive error: {exc}")
                return

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"[{run_id}] Received non-JSON message — ignoring")
                continue

            if message.get("type") == "hitl_response":
                _handle_hitl_response(run_id, message)

    send_task = asyncio.create_task(send_events())
    recv_task = asyncio.create_task(receive_messages())

    try:
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except WebSocketDisconnect:
        logger.info(f"[{run_id}] WebSocket disconnected during gather")
    except Exception as exc:
        logger.warning(f"[{run_id}] WebSocket stream error: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _handle_hitl_response(run_id: str, message: dict) -> None:
    """Process a hitl_response message from the client.

    Validates the approved_claims list, writes it to the callback's hitl_response
    dict, and sets the hitl_event to wake the paused hitl node.
    """
    cb = get_callback(run_id)
    if cb is None or cb.hitl_event is None:
        logger.warning(f"[{run_id}] Received hitl_response but no HITL event registered — ignoring")
        return

    raw_claims = message.get("approved_claims", [])
    validated: list[dict] = []

    for claim in raw_claims:
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("text", "")).strip()
        if not text or len(text) > 500:
            logger.warning(f"[{run_id}] Skipping invalid claim from client: {claim!r}")
            continue
        claim = dict(claim)
        if not claim.get("id"):
            claim["id"] = str(uuid.uuid4())
        if "importance_score" not in claim:
            claim["importance_score"] = 1.0
        validated.append(claim)

    cb.hitl_response["approved_claims"] = validated
    cb.hitl_event.set()
    logger.info(f"[{run_id}] HITL response received — {len(validated)} approved claims, event set")


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
