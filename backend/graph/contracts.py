"""
Typed contracts for the PR Critic pipeline.

The graph still passes a shared mutable state mapping between agents, but these
TypedDict views make each agent's input/output boundary explicit and keep the
public API payload unchanged.
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
    review: str
    strategy: str
    score: float
    score_rationale: str
    issues: list[str]


class PRCriticState(TypedDict):
    pr_url: str
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    retrieval_sources: list[str]
    candidates: list[ReviewCandidate]
    trigger_branch: bool
    best_candidate: ReviewCandidate | None
    selector_rationale: str
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class FetchAgentInput(TypedDict):
    pr_url: str
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class FetchAgentOutput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    trace: list[TraceEvent]


class RagAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class RagAgentOutput(TypedDict):
    retrieved_context: str
    retrieval_sources: list[str]
    trace: list[TraceEvent]


class ReviewAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    retrieval_sources: list[str]
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class ReviewAgentOutput(TypedDict):
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]


class CriticAgentInput(TypedDict):
    pr_diff: str
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class CriticAgentOutput(TypedDict):
    candidates: NotRequired[list[ReviewCandidate]]
    trigger_branch: bool
    trace: list[TraceEvent]


class BranchAgentInput(TypedDict):
    pr_diff: str
    pr_metadata: PRMetadata
    retrieved_context: str
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class BranchAgentOutput(TypedDict):
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]


class SelectorAgentInput(TypedDict):
    pr_diff: str
    candidates: list[ReviewCandidate]
    trace: list[TraceEvent]
    request_context: NotRequired[RequestContext]


class SelectorAgentOutput(TypedDict):
    best_candidate: ReviewCandidate | None
    selector_rationale: str
    trace: list[TraceEvent]


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
        "candidates": [],
        "trigger_branch": False,
        "best_candidate": None,
        "selector_rationale": "",
        "trace": [],
    }
    if request_context is not None:
        state["request_context"] = request_context
    return state
