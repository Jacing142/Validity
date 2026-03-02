import logging
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.models import OverallVerdict, VerifyRequest, VerifyResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Validity API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "search_provider": settings.SEARCH_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
    }


@app.post("/api/verify", response_model=VerifyResponse)
async def verify(request: VerifyRequest):
    run_id = str(uuid.uuid4())
    logger.info(f"[{run_id}] Starting verification for text ({len(request.text)} chars)")

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

        logger.info(f"[{run_id}] Invoking verification graph")
        final_state = await verification_graph.ainvoke(initial_state)

        if final_state.get("errors"):
            logger.warning(f"[{run_id}] Pipeline completed with errors: {final_state['errors']}")

        overall = final_state.get("overall_verdict")
        if overall is None:
            return VerifyResponse(
                run_id=run_id,
                status="error",
                error="Pipeline completed but produced no verdict",
            )

        verdict = OverallVerdict(**overall) if isinstance(overall, dict) else overall

        logger.info(f"[{run_id}] Verification complete — verdict: {verdict.verdict}")
        return VerifyResponse(run_id=run_id, status="completed", result=verdict)

    except Exception as e:
        logger.exception(f"[{run_id}] Fatal error during verification")
        return VerifyResponse(run_id=run_id, status="error", error=str(e))
