import logging
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise claim extraction assistant. Your job is to extract every atomic, verifiable factual claim from the input text.

Rules:
- Each claim must be a single, self-contained factual statement that can be independently verified.
- Exclude opinions, subjective statements, vague assertions, predictions, and normative claims.
- Include only claims that are objectively true or false — claims that could, in principle, be checked against evidence.
- Do NOT rephrase or interpret — extract the claim as close to the original wording as possible.
- Each claim should be understandable without reading the original text (i.e., self-contained).

Examples:

Input: "The Eiffel Tower is 330 metres tall and was completed in 1889. It is one of the most beautiful structures ever built. Over 7 million people visit it annually, making it the most-visited paid monument in the world."

Output:
{
  "claims": [
    {"text": "The Eiffel Tower is 330 metres tall"},
    {"text": "The Eiffel Tower was completed in 1889"},
    {"text": "Over 7 million people visit the Eiffel Tower annually"},
    {"text": "The Eiffel Tower is the most-visited paid monument in the world"}
  ]
}

Note: "It is one of the most beautiful structures ever built" is excluded — it is a subjective opinion, not a verifiable fact.

Input: "Tesla reported $96.8 billion in revenue for 2023. The company makes the best electric vehicles on the market. Their Model Y was the world's best-selling car in 2023, with 1.2 million units sold."

Output:
{
  "claims": [
    {"text": "Tesla reported $96.8 billion in revenue for 2023"},
    {"text": "The Tesla Model Y was the world's best-selling car in 2023"},
    {"text": "The Tesla Model Y sold 1.2 million units in 2023"}
  ]
}

Note: "The company makes the best electric vehicles on the market" is excluded — it is a subjective assertion, not a verifiable fact.

Return a JSON object with this exact structure:
{
  "claims": [
    {"text": "The atomic claim as a complete, self-contained sentence"},
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
            claims.append({
                "id": str(uuid.uuid4()),
                "text": claim_text,
                "importance_score": 0.0,
            })

        elapsed = time.time() - start
        logger.info(f"[{run_id}] [decompose] Extracted {len(claims)} claims in {elapsed:.2f}s")

        if cb:
            cb.emit({
                "type": "node_event",
                "node": "decompose",
                "status": "completed",
                "detail": f"Found {len(claims)} atomic claim{'s' if len(claims) != 1 else ''} in the input",
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
