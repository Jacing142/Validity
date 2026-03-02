import json
import logging
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import get_llm
from backend.agents.state import VerificationState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise claim extraction assistant. Your job is to extract every atomic, verifiable factual claim from the input text.

Rules:
- Each claim must be a single, self-contained factual statement that can be independently verified.
- Exclude opinions, subjective statements, vague assertions, predictions, and normative claims.
- Include only claims that are objectively true or false — claims that could, in principle, be checked against evidence.
- Do NOT rephrase or interpret — extract the claim as close to the original wording as possible.
- Each claim should be understandable without reading the original text (i.e., self-contained).

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

    try:
        llm = get_llm(complexity="high")
        input_text = state["input_text"]

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Extract all atomic, verifiable factual claims from this text:\n\n{input_text}"),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)
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
        return {"claims": claims}

    except Exception as e:
        logger.exception(f"[{run_id}] [decompose] Failed")
        errors = list(state.get("errors", []))
        errors.append(f"decompose: {str(e)}")
        return {"claims": [], "errors": errors}
