"""
Validity MCP Server — exposes the verification pipeline as Claude Desktop tools.

Three tools:
    verify_text               — Full pipeline, HITL auto-approved, returns formatted verdict
    verify_text_interactive   — Two-step: step 1 returns ranked claims, step 2 verifies selected ones
    get_run                   — Retrieve a previous run's verdict from the in-process store

Entry point:
    python -m mcp.server

Note: get_run only works for runs started in this same MCP server process.
      Runs initiated via the FastAPI web server are not accessible here.
"""

import logging
import os
import sys
import uuid

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so backend.* imports resolve correctly
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process run store
# Stores results from verify_text and verify_text_interactive calls.
# Also used as a preview cache for verify_text_interactive step 1 → step 2.
# ---------------------------------------------------------------------------
_run_store: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="Validity",
    instructions=(
        "Validity verifies factual claims in text using adversarial web search "
        "and LLM evidence analysis. Use verify_text for automatic verification "
        "or verify_text_interactive to review and select claims first."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_initial_state(text: str, run_id: str) -> dict:
    return {
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


def _format_verdict(verdict: dict) -> str:
    """Format an OverallVerdict dict as human-readable text."""
    lines = [
        f"Overall Verdict: {verdict['verdict'].upper()}",
        f"Summary: {verdict['summary']}",
        "",
        f"Claims Verified: {verdict['total_claims']}",
    ]

    for i, cv in enumerate(verdict.get("claim_verdicts", []), 1):
        lines.append("")
        lines.append(f'{i}. "{cv["claim_text"]}"')
        lines.append(
            f'   Verdict: {cv["verdict"].upper()} (confidence: {cv["confidence"]:.2f})'
        )

        # Build source summary
        source_parts = []
        for src in cv.get("sources", []):
            tier = (src.get("source_tier") or "low").upper()
            raw_url = src.get("url", "")
            domain = (
                raw_url.replace("https://", "")
                .replace("http://", "")
                .split("/")[0]
            )
            # Check if this source contradicts
            is_contradiction = any(
                ea.get("assessment") == "contradicts"
                and ea.get("source", {}).get("url") == src.get("url")
                for ea in cv.get("contradicting_evidence", [])
            )
            label = f"{domain} ({tier})"
            if is_contradiction:
                label += " — CONTRADICTS"
            source_parts.append(label)

        if source_parts:
            lines.append(f'   Sources: {", ".join(source_parts)}')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1: verify_text
# ---------------------------------------------------------------------------

@mcp.tool
async def verify_text(text: str) -> str:
    """Run the full claim verification pipeline on the provided text.

    HITL (human-in-the-loop) is automatically approved — all ranked claims
    are verified without user intervention. The pipeline:
      1. Decomposes text into atomic claims
      2. Ranks claims by verifiability and importance
      3. Generates adversarial search queries (affirm + refute per claim)
      4. Searches the web
      5. Classifies source credibility by domain tier (high/mid/low)
      6. Weighs evidence and assigns per-claim verdicts
      7. Synthesizes an overall verdict

    Args:
        text: The text to verify. Should contain factual claims (1–3 paragraphs).

    Returns:
        A formatted verdict with overall assessment and per-claim results.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"[MCP] verify_text run_id={run_id}")

    from backend.agents.graph import verification_graph
    from backend.models import OverallVerdict

    initial_state = _make_initial_state(text, run_id)

    # No StreamingCallbackHandler registered → hitl_node sees cb=None → auto-approves
    final_state = await verification_graph.ainvoke(initial_state)

    overall = final_state.get("overall_verdict")
    if overall is None:
        return "Error: Pipeline completed but produced no overall verdict."

    verdict_dict = overall if isinstance(overall, dict) else overall.model_dump()

    # Store for get_run
    _run_store[run_id] = {
        "run_id": run_id,
        "status": "completed",
        "result": verdict_dict,
    }

    logger.info(f"[MCP] verify_text complete — verdict: {verdict_dict.get('verdict')}")
    return f"Run ID: {run_id}\n\n" + _format_verdict(verdict_dict)


# ---------------------------------------------------------------------------
# Tool 2: verify_text_interactive
# ---------------------------------------------------------------------------

@mcp.tool
async def verify_text_interactive(
    text: str,
    approved_claim_ids: list[str] | None = None,
    preview_id: str | None = None,
) -> str:
    """Two-step interactive claim verification.

    Step 1 — Call with text only (omit approved_claim_ids and preview_id):
        Decomposes and ranks claims. Returns claim IDs, texts, and importance scores.
        Also returns a preview_id. Note this ID for step 2.

    Step 2 — Call with text + approved_claim_ids + preview_id:
        Runs the full verification pipeline on only the approved claims.
        Returns a formatted verdict. The preview_id links back to the step 1 results.

    Each call pair is independent — the preview cache is in-process only.

    Args:
        text:               The text to verify.
        approved_claim_ids: Claim IDs (from step 1) to verify. Omit for step 1.
        preview_id:         The preview_id returned in step 1. Required for step 2.

    Returns:
        Step 1: List of ranked claims with IDs.
        Step 2: Formatted verdict for the selected claims.
    """
    from backend.agents.nodes.decompose import decompose_node
    from backend.agents.nodes.reformulate import reformulate_node
    from backend.agents.nodes.rank import rank_node

    # --- Step 2: look up stored step-1 claims ---
    if approved_claim_ids and preview_id:
        entry = _run_store.get(preview_id)
        if entry and entry.get("type") == "preview":
            ranked_claims = entry.get("ranked_claims", [])
            approved_set = set(approved_claim_ids)
            approved_claims = [c for c in ranked_claims if c["id"] in approved_set]

            if not approved_claims:
                return (
                    "No claims matched the provided IDs. "
                    "Ensure you're using the IDs from the step 1 output "
                    f"(preview_id: {preview_id})."
                )

            return await _run_from_approved_claims(text, approved_claims)

    # --- Step 1: decompose → reformulate → rank ---
    run_id = str(uuid.uuid4())
    logger.info(f"[MCP] verify_text_interactive step 1 preview_id={run_id}")

    state = _make_initial_state(text, run_id)

    # decompose is sync; reformulate is async; rank is sync
    state.update(decompose_node(state))
    state.update(await reformulate_node(state))  # async node
    state.update(rank_node(state))

    ranked_claims = state.get("ranked_claims", [])

    # Cache so step 2 can retrieve exact IDs
    _run_store[run_id] = {
        "run_id": run_id,
        "type": "preview",
        "ranked_claims": ranked_claims,
    }

    lines = [
        "Step 1 of 2 — Review the ranked claims below.",
        f"Preview ID: {run_id}",
        "",
        f"Found {len(ranked_claims)} ranked claim(s):",
        "",
    ]
    for i, claim in enumerate(ranked_claims, 1):
        lines.append(f'{i}. ID: {claim["id"]}')
        lines.append(f'   "{claim["text"]}"')
        lines.append(f'   Importance: {claim["importance_score"]:.2f}')
        lines.append("")

    lines.extend([
        "To verify specific claims, call verify_text_interactive again with:",
        '  text            = <same text as above>',
        '  preview_id      = "' + run_id + '"',
        '  approved_claim_ids = ["<id1>", "<id2>", ...]',
        "",
        "To verify all claims, call verify_text instead.",
    ])

    return "\n".join(lines)


async def _run_from_approved_claims(text: str, approved_claims: list[dict]) -> str:
    """Run the pipeline from query_gen onward with a pre-approved claim list."""
    from backend.agents.nodes.query_gen import query_gen_node
    from backend.agents.nodes.search import search_node
    from backend.agents.nodes.classify import classify_node
    from backend.agents.nodes.weigh import weigh_node
    from backend.agents.nodes.verdict import verdict_node
    from backend.agents.nodes.synthesize import synthesize_node

    run_id = str(uuid.uuid4())
    logger.info(f"[MCP] verify_text_interactive step 2 run_id={run_id} claims={len(approved_claims)}")

    state = _make_initial_state(text, run_id)
    state["approved_claims"] = approved_claims

    # Run pipeline from query_gen (skip decompose/reformulate/rank/hitl)
    state.update(query_gen_node(state))
    state.update(await search_node(state))      # async
    state.update(await classify_node(state))    # async (LLM fallback for unknown domains)
    state.update(await weigh_node(state))       # async
    state.update(await verdict_node(state))     # async
    state.update(synthesize_node(state))

    overall = state.get("overall_verdict")
    if overall is None:
        return "Error: Pipeline completed but produced no overall verdict."

    verdict_dict = overall if isinstance(overall, dict) else overall.model_dump()

    _run_store[run_id] = {
        "run_id": run_id,
        "status": "completed",
        "result": verdict_dict,
    }

    logger.info(f"[MCP] verify_text_interactive step 2 complete — verdict: {verdict_dict.get('verdict')}")
    return f"Run ID: {run_id}\n\n" + _format_verdict(verdict_dict)


# ---------------------------------------------------------------------------
# Tool 3: get_run
# ---------------------------------------------------------------------------

@mcp.tool
def get_run(run_id: str) -> str:
    """Retrieve the result of a previous verification run by its run_id.

    Note: This only works for runs started in this MCP server process.
    Runs initiated through the web UI (FastAPI server) are not accessible here,
    as the run store is in-memory and not shared across processes.

    Args:
        run_id: The run ID returned by verify_text or verify_text_interactive.

    Returns:
        Formatted verdict if the run is complete, status if still running,
        or a "not found" message if the run_id is unknown.
    """
    entry = _run_store.get(run_id)

    if entry is None:
        return (
            f"Run '{run_id}' not found.\n\n"
            "Note: get_run only works for runs started in this MCP server process. "
            "If you started the run via the web UI, use GET /api/verify/{run_id}/result instead."
        )

    if entry.get("type") == "preview":
        return (
            f"Run '{run_id}' is a step-1 preview (ranked claims only, not yet verified). "
            "Call verify_text_interactive with this preview_id and approved_claim_ids to complete."
        )

    status = entry.get("status", "unknown")
    if status == "running":
        return f"Run '{run_id}' is still in progress."

    if status == "error":
        return f"Run '{run_id}' failed: {entry.get('error', 'Unknown error')}"

    verdict_dict = entry.get("result")
    if verdict_dict:
        return f"Run '{run_id}' — completed\n\n" + _format_verdict(verdict_dict)

    return f"Run '{run_id}' status: {status}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
