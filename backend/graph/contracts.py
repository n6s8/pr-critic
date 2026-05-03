"""
Typed contracts for the PR Critic pipeline.

The graph passes a shared mutable state mapping between agents. These
TypedDict views make each agent's input/output boundary explicit and keep the
backend state aligned with the API contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

ExecutionMode = Literal["sync", "async_threadpool"]


class RequestContext(TypedDict):
    request_id: str
    submitted_at: str
    execution_mode: ExecutionMode
    route_path: str


class TraceEvent(TypedDict):
    ts: str
    agent: str
    event: str
    data: dict[str, Any]
    duration_ms: NotRequired[float]
    request_id: NotRequired[str]


class PRMetadata(TypedDict, total=False):
    title: str
    author: str
    base_branch: str
    head_branch: str
    files_changed: list[str]
    language: str
    pr_url: str
    error: str


class ReviewCandidate(TypedDict):
    id: str
    review: str
    strategy: str


class CandidateScore(TypedDict):
    candidate_index: int
    strategy: str
    score: float
    rationale: str
    issues_identified: list[str]


class RetrievalHit(TypedDict):
    source: str
    section: str
    snippet: str
    relevance: float


class RepoLintIssue(TypedDict):
    tool: str
    file: str
    line: int
    code: str
    message: str


class RepoSignals(TypedDict):
    checkout_status: str
    lint_status: str
    file_types: list[str]
    lint_issue_count: int
    lint_issues: list[RepoLintIssue]
    summary: str


class ReviewPlan(TypedDict, total=False):
    focus: str
    rationale: str
    risk_terms: list[str]
    expected_issue_types: list[str]


class GroundedIssue(TypedDict, total=False):
    severity: str
    issue_type: str
    file: str
    line: int
    message: str
    code_snippet: str
    source_id: str
    candidate_index: int


class PRCriticState(TypedDict):
    pr_url: str
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    retrieval_sources: list[str]
    retrieval_hits: list[RetrievalHit]
    repo_signals: RepoSignals
    candidates: list[ReviewCandidate]
    scores: list[CandidateScore]
    branch_taken: bool
    branch_improvement: float | None
    selected_index: int | None
    selector_reason: str
    rate_limited: bool
    large_pr_mode: bool
    request_cache_key: str
    branch_skipped_reason: str
    llm_input_tokens: int
    branch_budget_available: bool
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]
    candidate_grounded_issues: NotRequired[dict[str, list[GroundedIssue]]]
    grounded_issues: NotRequired[list[GroundedIssue]]
    synthesis_report: NotRequired[dict[str, Any]]


class FetchAgentInput(TypedDict):
    pr_url: str
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    request_context: NotRequired[RequestContext]


class FetchAgentOutput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    trace: list[TraceEvent]


class RagAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]


class RagAgentOutput(TypedDict):
    retrieved_context: str
    retrieval_sources: list[str]
    retrieval_hits: list[RetrievalHit]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    trace: list[TraceEvent]
    agent_messages: NotRequired[list[dict[str, Any]]]


class ReviewAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    retrieval_sources: list[str]
    retrieval_hits: list[RetrievalHit]
    repo_signals: NotRequired[RepoSignals]
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]


class ReviewAgentOutput(TypedDict):
    candidates: list[ReviewCandidate]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    trace: list[TraceEvent]
    agent_messages: NotRequired[list[dict[str, Any]]]


class CriticAgentInput(TypedDict):
    pr_diff: str
    candidates: list[ReviewCandidate]
    scores: list[CandidateScore]
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]


class CriticAgentOutput(TypedDict):
    scores: list[CandidateScore]
    branch_taken: NotRequired[bool]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    trace: list[TraceEvent]
    agent_messages: NotRequired[list[dict[str, Any]]]


class BranchAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    scores: list[CandidateScore]
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]


class BranchAgentOutput(TypedDict):
    candidates: list[ReviewCandidate]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    trace: list[TraceEvent]
    agent_messages: NotRequired[list[dict[str, Any]]]


class SelectorAgentInput(TypedDict):
    pr_diff: str
    candidates: list[ReviewCandidate]
    scores: list[CandidateScore]
    branch_taken: bool
    trace: list[TraceEvent]
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    request_context: NotRequired[RequestContext]
    review_plan: NotRequired[ReviewPlan]
    safety_flags: NotRequired[dict[str, Any]]
    agent_messages: NotRequired[list[dict[str, Any]]]
    candidate_grounded_issues: NotRequired[dict[str, list[GroundedIssue]]]
    grounded_issues: NotRequired[list[GroundedIssue]]
    synthesis_report: NotRequired[dict[str, Any]]


class SelectorAgentOutput(TypedDict):
    candidates: NotRequired[list[ReviewCandidate]]
    selected_index: int | None
    selector_reason: str
    branch_improvement: float | None
    rate_limited: NotRequired[bool]
    large_pr_mode: NotRequired[bool]
    repo_signals: NotRequired[RepoSignals]
    request_cache_key: NotRequired[str]
    branch_skipped_reason: NotRequired[str]
    llm_input_tokens: NotRequired[int]
    branch_budget_available: NotRequired[bool]
    trace: list[TraceEvent]
    agent_messages: NotRequired[list[dict[str, Any]]]
    grounded_issues: NotRequired[list[GroundedIssue]]
    synthesis_report: NotRequired[dict[str, Any]]


def build_request_context(
    request_id: str,
    *,
    execution_mode: ExecutionMode = "sync",
    route_path: str = "/review",
) -> RequestContext:
    return {
        "request_id": request_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": execution_mode,
        "route_path": route_path,
    }


def build_initial_state(
    pr_url: str,
    *,
    request_context: RequestContext | None = None,
) -> PRCriticState:
    state: PRCriticState = {
        "pr_url": pr_url,
        "pr_diff": "",
        "pr_metadata": {},
        "retrieved_context": "",
        "retrieval_sources": [],
        "retrieval_hits": [],
        "repo_signals": {
            "checkout_status": "not_requested",
            "lint_status": "not_requested",
            "file_types": [],
            "lint_issue_count": 0,
            "lint_issues": [],
            "summary": "",
        },
        "candidates": [],
        "scores": [],
        "branch_taken": False,
        "branch_improvement": None,
        "selected_index": None,
        "selector_reason": "",
        "rate_limited": False,
        "large_pr_mode": False,
        "request_cache_key": "",
        "branch_skipped_reason": "",
        "llm_input_tokens": 0,
        "branch_budget_available": True,
        "trace": [],
        "review_plan": {},
        "safety_flags": {},
        "agent_messages": [],
        "candidate_grounded_issues": {},
        "grounded_issues": [],
        "synthesis_report": {},
    }
    if request_context is not None:
        state["request_context"] = request_context
    return state
