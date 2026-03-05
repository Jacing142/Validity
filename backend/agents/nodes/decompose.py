import logging
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState
from backend.agents.callbacks import get as get_callback
from backend.agents.utils import parse_llm_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a statement extraction assistant. Your only job is to find every atomic statement in the input text. You are NOT a fact-checker — do not decide if something is true, important, or worth checking.

Rules:
- Extract EVERY statement that asserts something, including opinions, superlatives, and subjective claims
- Do NOT filter or discard any statement — extraction only, no judgment
- Each statement must be self-contained and understandable without the original text
- Tag each with claim_type: "verifiable" (specific fact, number, date, named event) or "subjective" (opinion, superlative, vague assertion)
- Maximum 8 statements. If more exist, take the 8 most distinct ones.
- If you are unsure whether to include something, INCLUDE IT and tag it subjective

Examples:

Input: "The Eiffel Tower is 330 metres tall. It is one of the most beautiful structures ever built. Over 7 million people visit it annually."
Output:
{
  "claims": [
    {"text": "The Eiffel Tower is 330 metres tall", "claim_type": "verifiable"},
    {"text": "The Eiffel Tower is one of the most beautiful structures ever built", "claim_type": "subjective"},
    {"text": "Over 7 million people visit the Eiffel Tower annually", "claim_type": "verifiable"}
  ]
}

Input: "Apple makes the best laptops in the world. Their M3 chip was released in 2023. Customer service is incredible."
Output:
{
  "claims": [
    {"text": "Apple makes the best laptops in the world", "claim_type": "subjective"},
    {"text": "Apple's M3 chip was released in 2023", "claim_type": "verifiable"},
    {"text": "Apple's customer service is incredible", "claim_type": "subjective"}
  ]
}

Input: "Pizza is the best food in America. Shakespeare wrote Hamlet around 1600. Einstein was the greatest physicist ever."
Output:
{
  "claims": [
    {"text": "Pizza is the best food in America", "claim_type": "subjective"},
    {"text": "Shakespeare wrote Hamlet around 1600", "claim_type": "verifiable"},
    {"text": "Einstein was the greatest physicist ever", "claim_type": "subjective"}
  ]
}

Return a JSON object with this exact structure:
{
  "claims": [
    {"text": "statement text", "claim_type": "verifiable" | "subjective"},
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
