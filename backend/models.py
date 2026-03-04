from pydantic import BaseModel, field_validator


class Claim(BaseModel):
    id: str                          # UUID
    text: str                        # The atomic claim
    importance_score: float = 0.0    # 0-1, from ranking node


class SearchQuery(BaseModel):
    claim_id: str
    query: str
    intent: str                      # "affirm" | "refute"


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    query_intent: str                # "affirm" | "refute"
    source_tier: str | None = None   # "high" | "mid" | "low"


class EvidenceAssessment(BaseModel):
    claim_id: str
    source: SearchResult
    assessment: str                  # "supports" | "contradicts" | "irrelevant"
    reasoning: str                   # One-line LLM explanation
    weight: float                    # Tier-adjusted weight


class ClaimVerdict(BaseModel):
    claim_id: str
    claim_text: str
    verdict: str                     # "high" | "medium" | "low" | "contradicted"
    confidence: float                # 0-1
    supporting_evidence: list[EvidenceAssessment]
    contradicting_evidence: list[EvidenceAssessment]
    sources: list[SearchResult]


class OverallVerdict(BaseModel):
    summary: str
    verdict: str                     # "high" | "medium" | "low" | "mixed"
    claim_verdicts: list[ClaimVerdict]
    total_claims: int
    high_validity_count: int
    medium_validity_count: int
    low_validity_count: int
    contradicted_count: int
    errors: list[str] = []


class VerifyRequest(BaseModel):
    text: str

    @field_validator('text')
    @classmethod
    def validate_text_length(cls, v):
        v = v.strip()
        if len(v) < 50:
            raise ValueError('Text must be at least 50 characters. Provide a paragraph with factual claims to verify.')
        if len(v) > 5000:
            raise ValueError('Text must be 5000 characters or fewer. Submit a shorter passage.')
        return v


class VerifyResponse(BaseModel):
    run_id: str
    status: str                      # "completed" | "error"
    result: OverallVerdict | None = None
    error: str | None = None
