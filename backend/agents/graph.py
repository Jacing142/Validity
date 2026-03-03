import logging

from langgraph.graph import END, START, StateGraph

from backend.agents.state import VerificationState
from backend.agents.nodes.decompose import decompose_node
from backend.agents.nodes.rank import rank_node
from backend.agents.nodes.hitl import hitl_node
from backend.agents.nodes.query_gen import query_gen_node
from backend.agents.nodes.search import search_node
from backend.agents.nodes.classify import classify_node
from backend.agents.nodes.weigh import weigh_node
from backend.agents.nodes.verdict import verdict_node
from backend.agents.nodes.synthesize import synthesize_node

logger = logging.getLogger(__name__)


def _no_claims_node(state: VerificationState) -> dict:
    """Short-circuit node reached when the user approves zero claims after HITL review.

    Sets overall_verdict to a valid OverallVerdict dict with total_claims=0
    so _run_pipeline can emit a normal pipeline_complete event.
    """
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [no_claims] User approved 0 claims — short-circuiting pipeline")

    from backend.agents.callbacks import get as get_callback
    cb = get_callback(run_id)
    if cb:
        cb.emit({
            "type": "node_event",
            "node": "hitl",
            "status": "completed",
            "detail": "No claims selected for verification.",
        })

    return {
        "overall_verdict": {
            "verdict": "low",
            "summary": (
                "No claims were selected for verification. "
                "The pipeline was stopped after the claim review step."
            ),
            "claim_verdicts": [],
            "total_claims": 0,
            "high_validity_count": 0,
            "medium_validity_count": 0,
            "low_validity_count": 0,
            "contradicted_count": 0,
        }
    }


def _route_after_hitl(state: VerificationState) -> str:
    """Conditional router: proceed to query_gen if any claims were approved, else short-circuit."""
    if not state.get("approved_claims"):
        return "no_claims"
    return "query_gen"


# ---------------------------------------------------------------------------
# Build the LangGraph state graph
# ---------------------------------------------------------------------------

graph = StateGraph(VerificationState)

# Register all nodes
graph.add_node("decompose", decompose_node)
graph.add_node("rank", rank_node)
graph.add_node("hitl", hitl_node)            # Phase 3: HITL pause/resume node
graph.add_node("no_claims", _no_claims_node)  # Phase 3: zero-claim short-circuit
graph.add_node("query_gen", query_gen_node)
graph.add_node("search", search_node)
graph.add_node("classify", classify_node)
graph.add_node("weigh", weigh_node)
graph.add_node("verdict", verdict_node)
graph.add_node("synthesize", synthesize_node)

# Phase 3: rank → hitl → [conditional] → query_gen  (or → no_claims → END)
graph.add_edge(START, "decompose")
graph.add_edge("decompose", "rank")
graph.add_edge("rank", "hitl")
graph.add_conditional_edges(
    "hitl",
    _route_after_hitl,
    {"query_gen": "query_gen", "no_claims": "no_claims"},
)
graph.add_edge("no_claims", END)
graph.add_edge("query_gen", "search")
graph.add_edge("search", "classify")
graph.add_edge("classify", "weigh")
graph.add_edge("weigh", "verdict")
graph.add_edge("verdict", "synthesize")
graph.add_edge("synthesize", END)

verification_graph = graph.compile()
