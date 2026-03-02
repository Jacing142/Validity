"""Mock LLM for development/testing when real API keys are not available.

Returns deterministic, realistic-looking responses based on prompt pattern matching.
Allows the full LangGraph pipeline to run end-to-end for demonstration.

NOTE: This is for architecture validation and demo purposes only.
      Use a real LLM provider (openai or anthropic) for production.
"""

import json
import re
from typing import Any, Iterator, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def _detect_intent(messages: list[BaseMessage]) -> str:
    """Identify what kind of pipeline node is calling the LLM."""
    system_content = ""
    human_content = ""
    for msg in messages:
        if hasattr(msg, "type"):
            if msg.type == "system":
                system_content = msg.content.lower()
            elif msg.type == "human":
                human_content = msg.content.lower()

    if "atomic" in system_content and "verifiable" in system_content:
        return "decompose"
    if "verifiability" in system_content and "importance" in system_content:
        return "rank"
    if "adversarial" in system_content and "affirm" in system_content:
        return "query_gen"
    # Verdict detection: system prompt has "validity verdict" and "confidence"
    if ("validity verdict" in system_content or "verdict assignment" in system_content) and "confidence" in system_content:
        return "verdict"
    # Weigh detection: system prompt has SUPPORTS / CONTRADICTS / IRRELEVANT
    if "supports" in system_content and "contradicts" in system_content and "irrelevant" in system_content:
        return "weigh"
    if "synthesis" in system_content or "synthesize" in system_content or "aggregate" in system_content or "per-claim verdicts" in system_content:
        return "synthesize"
    return "unknown"


def _mock_decompose(human_content: str) -> str:
    """Extract claims from text using simple sentence splitting."""
    # Find the input text
    text_match = re.search(r"from this text:\n\n(.+)", human_content, re.DOTALL)
    if not text_match:
        text_match = re.search(r"text:\n\n(.+)", human_content, re.DOTALL)
    text = text_match.group(1).strip() if text_match else human_content

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) > 10 and not s.startswith("Note") and not s.startswith("According to my"):
            claims.append({"text": s})

    return json.dumps({"claims": claims})


def _mock_rank(human_content: str) -> str:
    """Score claims with reasonable scores."""
    claims_match = re.search(r"\[(.+)\]", human_content, re.DOTALL)
    claims_data = []
    if claims_match:
        try:
            claims_data = json.loads("[" + claims_match.group(1) + "]")
        except Exception:
            pass

    scored = []
    for claim in claims_data:
        cid = claim.get("id", "")
        text = claim.get("text", "").lower()
        # Assign scores based on content clues
        if "great wall" in text and "space" in text:
            v, i = 0.95, 0.90  # famous myth — highly verifiable, important
        elif "earth" in text and "sun" in text:
            v, i = 0.99, 0.85
        elif "water" in text and "boil" in text:
            v, i = 0.98, 0.80
        else:
            v, i = 0.75, 0.70
        scored.append({"id": cid, "verifiability": v, "importance": i, "combined_score": (v + i) / 2})

    return json.dumps({"scored_claims": scored})


def _mock_query_gen(human_content: str) -> str:
    """Generate adversarial queries for each claim."""
    claims_match = re.search(r"\[(.+)\]", human_content, re.DOTALL)
    claims_data = []
    if claims_match:
        try:
            claims_data = json.loads("[" + claims_match.group(1) + "]")
        except Exception:
            pass

    queries = []
    for claim in claims_data:
        cid = claim.get("id", "")
        text = claim.get("text", "")
        # Generate generic affirm/refute pairs based on claim text
        words = text.replace(".", "").replace(",", "").split()[:6]
        base = " ".join(words)
        queries.extend([
            {"claim_id": cid, "intent": "affirm", "query": f"{base} evidence facts"},
            {"claim_id": cid, "intent": "affirm", "query": f"{base} scientific proof data"},
            {"claim_id": cid, "intent": "refute", "query": f"{base} myth debunked false"},
            {"claim_id": cid, "intent": "refute", "query": f"{base} incorrect wrong disproven"},
        ])

    return json.dumps({"queries": queries})


def _mock_weigh(human_content: str) -> str:
    """Generate evidence assessments for sources."""
    # Parse sources from the human message
    sources_match = re.search(r'"url":\s*"([^"]+)"', human_content)
    claim_text = ""
    claim_match = re.search(r"Claim:\s*(.+?)(?:\n\n|Sources)", human_content, re.DOTALL)
    if claim_match:
        claim_text = claim_match.group(1).strip().lower()

    # Find all URLs
    urls = re.findall(r'"url":\s*"([^"]+)"', human_content)
    titles = re.findall(r'"title":\s*"([^"]+)"', human_content)

    assessments = []
    for i, url in enumerate(urls):
        title = titles[i] if i < len(titles) else ""
        # Determine assessment based on URL tier and claim content
        domain = url.split("/")[2] if "/" in url else url

        if "great wall" in claim_text and "space" in claim_text:
            # This is a famous myth - most credible sources will contradict it
            if any(d in domain for d in ["nasa", "gov", "edu", "space"]):
                assessments.append({
                    "source_url": url,
                    "assessment": "contradicts",
                    "reasoning": "NASA and scientific sources confirm the Great Wall is NOT visible from space with the naked eye.",
                })
            else:
                assessments.append({
                    "source_url": url,
                    "assessment": "contradicts",
                    "reasoning": "Source indicates the Great Wall of China is a common myth — it is not actually visible from space.",
                })
        elif "earth" in claim_text and "sun" in claim_text:
            assessments.append({
                "source_url": url,
                "assessment": "supports",
                "reasoning": "Source confirms Earth's heliocentric orbit around the Sun.",
            })
        elif "water" in claim_text and "boil" in claim_text:
            assessments.append({
                "source_url": url,
                "assessment": "supports",
                "reasoning": "Source confirms water boils at 100°C (212°F) at standard atmospheric pressure (sea level).",
            })
        else:
            assessments.append({
                "source_url": url,
                "assessment": "supports",
                "reasoning": f"Source '{title}' provides relevant supporting information.",
            })

    return json.dumps({"assessments": assessments})


def _mock_verdict(human_content: str) -> str:
    """Assign a verdict based on evidence summary."""
    claim_match = re.search(r"Claim:\s*(.+?)(?:\n\n|Weighted)", human_content, re.DOTALL)
    claim_text = claim_match.group(1).strip().lower() if claim_match else ""

    if "great wall" in claim_text and "space" in claim_text:
        return json.dumps({
            "verdict": "contradicted",
            "confidence": 0.97,
            "reasoning": "Multiple credible sources including NASA explicitly state the Great Wall of China is NOT visible from space with the naked eye, making this a well-documented myth.",
        })
    elif "earth" in claim_text and "sun" in claim_text:
        return json.dumps({
            "verdict": "high",
            "confidence": 0.99,
            "reasoning": "Heliocentric orbital mechanics is one of the most well-established scientific facts, supported by centuries of astronomical observation.",
        })
    elif "water" in claim_text and "boil" in claim_text:
        return json.dumps({
            "verdict": "high",
            "confidence": 0.99,
            "reasoning": "100°C as water's boiling point at sea level is a fundamental physical constant confirmed by countless scientific sources.",
        })
    else:
        return json.dumps({
            "verdict": "medium",
            "confidence": 0.60,
            "reasoning": "Mixed evidence found; further verification recommended.",
        })


def _mock_synthesize(human_content: str) -> str:
    """Synthesize an overall verdict."""
    # Count verdict types in the human content
    high_count = human_content.count('"verdict": "high"')
    contradicted_count = human_content.count('"verdict": "contradicted"')
    medium_count = human_content.count('"verdict": "medium"')
    low_count = human_content.count('"verdict": "low"')
    total = high_count + contradicted_count + medium_count + low_count

    if contradicted_count > 0 and high_count > 0:
        overall = "mixed"
        summary = (
            f"Of {total} verified claim(s), {high_count} received high validity ratings "
            f"and {contradicted_count} were contradicted by credible sources. "
            "The text contains a mixture of well-established scientific facts and at least one widely-debunked myth."
        )
    elif high_count == total and total > 0:
        overall = "high"
        summary = f"All {total} claim(s) are well-supported by credible evidence with high confidence."
    elif low_count > total // 2:
        overall = "low"
        summary = f"Most of the {total} claim(s) lack credible supporting evidence."
    else:
        overall = "medium"
        summary = f"The {total} claim(s) show mixed evidence quality requiring further investigation."

    return json.dumps({"verdict": overall, "summary": summary})


class MockChatModel(BaseChatModel):
    """A mock LangChain-compatible chat model for pipeline testing."""

    model_name: str = "mock-llm"

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        human_content = ""
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "human":
                human_content = msg.content

        intent = _detect_intent(messages)
        dispatch = {
            "decompose": _mock_decompose,
            "rank": _mock_rank,
            "query_gen": _mock_query_gen,
            "weigh": _mock_weigh,
            "verdict": _mock_verdict,
            "synthesize": _mock_synthesize,
        }

        handler = dispatch.get(intent, lambda x: json.dumps({"result": "mock response"}))
        content = handler(human_content)

        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, **kwargs)
