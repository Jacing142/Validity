import logging
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise claim extraction assistant. Your job is to extract every atomic claim from the input text — both factual and subjective.

Rules:
- Each claim must be a single, self-contained statement.
- Each claim should be understandable without reading the original text.
- Do NOT rephrase or interpret — extract the claim as close to the original wording as possible.
- Tag each claim with a claim_type:
  - "verifiable": The claim states a specific fact that can be checked against evidence (dates, numbers, named events, measurable assertions).
  - "subjective": The claim expresses an opinion, uses superlatives ("best", "worst", "most beautiful"), makes vague assertions, or cannot be directly verified via web search.
- Extract BOTH types. Do NOT discard subjective claims.
- Maximum 8 claims. If the text contains more, select the 8 most significant.

Examples:

Input: "The Eiffel Tower is 330 metres tall and was completed in 1889. It is one of the most beautiful structures ever built. Over 7 million people visit it annually."

Output:
{
  "claims": [
    {"text": "The Eiffel Tower is 330 metres tall", "claim_type": "verifiable"},
    {"text": "The Eiffel Tower was completed in 1889", "claim_type": "verifiable"},
    {"text": "The Eiffel Tower is one of the most beautiful structures ever built", "claim_type": "subjective"},
    {"text": "Over 7 million people visit the Eiffel Tower annually", "claim_type": "verifiable"}
  ]
}

Input: "Tesla reported $96.8 billion in revenue for 2023. The company makes the best electric vehicles on the market. Their Model Y was the world's best-selling car in 2023."

Output:
{
  "claims": [
    {"text": "Tesla reported $96.8 billion in revenue for 2023", "claim_type": "verifiable"},
    {"text": "Tesla makes the best electric vehicles on the market", "claim_type": "subjective"},
    {"text": "The Tesla Model Y was the world's best-selling car in 2023", "claim_type": "verifiable"}
  ]
}

Return a JSON object with this exact structure:
{
  "claims": [
    {"text": "The claim text", "claim_type": "verifiable" | "subjective"},
    ...
  ]
}

Return ONLY the JSON object, no other text."""


def decompose_node(state: VerificationState) -> dict:
    """Node 1: Extract atomic, verifiable claims from the input text."""
    run_id = state.get("run_id", "unknown")
    logger.info(f"[{run_id}] [decompose] Entering node")
    start = time.time()
    cb = get_callback(run_id)

    if cb:
        cb.emit({
            "type": "node_event",
            "node": "decompose",
            "status": "running",
            "detail": "Analyzing input text for factual claims...",
        })

    try:
        llm = get_llm(complexity="high")
        input_text = state["input_text"]

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Extract all atomic, verifiable factual claims from this text:\n\n{input_text}"),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        parsed = parse_llm_json(content)
        raw_claims = parsed.get("claims", [])

        claims = []
        for item in raw_claims:
            claim_text = item["text"] if isinstance(item, dict) else str(item)
            claim_type = item.get("claim_type", "verifiable") if isinstance(item, dict) else "verifiable"
            claims.append({
                "id": str(uuid.uuid4()),
                "text": claim_text,
                "claim_type": claim_type,
                "importance_score": 0.0,
                "original_text": claim_text,
                "reformulation_options": [],
            })

        elapsed = time.time() - start
        logger.info(f"[{run_id}] [decompose] Extracted {len(claims)} claims in {elapsed:.2f}s")

        verifiable = sum(1 for c in claims if c.get("claim_type") == "verifiable")
        subjective = len(claims) - verifiable
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "decompose",
                "status": "completed",
                "detail": f"Found {len(claims)} claims ({verifiable} verifiable, {subjective} subjective)",
                "data": {"claims": [c["text"] for c in claims]},
            })

        return {"claims": claims}

    except Exception as e:
        logger.exception(f"[{run_id}] [decompose] Failed")
        if cb:
            cb.emit({
                "type": "node_event",
                "node": "decompose",
                "status": "error",
                "detail": f"Decomposition failed: {str(e)}",
            })
        errors = list(state.get("errors", []))
        errors.append(f"decompose: {str(e)}")
        return {"claims": [], "errors": errors}
