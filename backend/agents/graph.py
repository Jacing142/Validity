import logging

from langgraph.graph import END, START, StateGraph

from backend.agents.state import VerificationState
from backend.agents.nodes.decompose import decompose_node
from backend.agents.nodes.rank import rank_node
from backend.agents.nodes.query_gen import query_gen_node
from backend.agents.nodes.search import search_node
from backend.agents.nodes.classify import classify_node
from backend.agents.nodes.weigh import weigh_node
from backend.agents.nodes.verdict import verdict_node
from backend.agents.nodes.synthesize import synthesize_node

logger = logging.getLogger(__name__)

# Build the LangGraph state graph
graph = StateGraph(VerificationState)

# Register all nodes
graph.add_node("decompose", decompose_node)
graph.add_node("rank", rank_node)
# TODO Phase 3: Insert HITL interrupt between rank and query_gen
graph.add_node("query_gen", query_gen_node)
graph.add_node("search", search_node)
graph.add_node("classify", classify_node)
graph.add_node("weigh", weigh_node)
graph.add_node("verdict", verdict_node)
graph.add_node("synthesize", synthesize_node)

# Linear flow — Phase 1 has no conditional edges
graph.add_edge(START, "decompose")
graph.add_edge("decompose", "rank")
# TODO Phase 3: edge from rank -> hitl -> query_gen replaces rank -> query_gen
graph.add_edge("rank", "query_gen")
graph.add_edge("query_gen", "search")
graph.add_edge("search", "classify")
graph.add_edge("classify", "weigh")
graph.add_edge("weigh", "verdict")
graph.add_edge("verdict", "synthesize")
graph.add_edge("synthesize", END)

verification_graph = graph.compile()
