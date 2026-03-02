from typing import TypedDict


class VerificationState(TypedDict):
    input_text: str
    claims: list[dict]
    ranked_claims: list[dict]
    approved_claims: list[dict]          # Same as ranked_claims in Phase 1
    search_queries: list[dict]
    search_results: list[dict]
    classified_results: list[dict]
    evidence_assessments: list[dict]
    claim_verdicts: list[dict]
    overall_verdict: dict | None
    run_id: str
    errors: list[str]
