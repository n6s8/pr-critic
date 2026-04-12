"""
Shared LangGraph state. Every agent reads from this dict and
returns only the keys it writes — LangGraph merges updates.
"""
from typing import TypedDict, Optional


class ReviewCandidate(TypedDict):
    review: str            # full review text
    strategy: str          # "initial" | "security_focus" | "minimal_style"
    score: float           # 0–10 assigned by Critic Agent
    score_rationale: str   # one-sentence explanation from Critic
    issues: list[str]      # list of issues identified by Critic


class PRCriticState(TypedDict):
    # Input
    pr_url: str
    pr_diff: str
    pr_metadata: dict

    # RAG
    retrieved_context: str
    retrieval_sources: list[str]

    # Candidates
    candidates: list[ReviewCandidate]

    # Routing
    trigger_branch: bool

    # Output
    best_candidate: Optional[ReviewCandidate]
    selector_rationale: str

    # Observability
    trace: list[dict]