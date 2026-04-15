"""
Backwards-compatible exports for the shared graph state.

The concrete TypedDict contracts live in backend.graph.contracts so agent
interfaces can reference narrower input/output views without changing the
existing graph state keys.
"""
from backend.graph.contracts import (
    BranchAgentInput,
    BranchAgentOutput,
    CriticAgentInput,
    CriticAgentOutput,
    FetchAgentInput,
    FetchAgentOutput,
    PRCriticState,
    PRMetadata,
    RagAgentInput,
    RagAgentOutput,
    RequestContext,
    ReviewAgentInput,
    ReviewAgentOutput,
    ReviewCandidate,
    SelectorAgentInput,
    SelectorAgentOutput,
    TraceEvent,
    build_initial_state,
    build_request_context,
)

__all__ = [
    "BranchAgentInput",
    "BranchAgentOutput",
    "CriticAgentInput",
    "CriticAgentOutput",
    "FetchAgentInput",
    "FetchAgentOutput",
    "PRCriticState",
    "PRMetadata",
    "RagAgentInput",
    "RagAgentOutput",
    "RequestContext",
    "ReviewAgentInput",
    "ReviewAgentOutput",
    "ReviewCandidate",
    "SelectorAgentInput",
    "SelectorAgentOutput",
    "TraceEvent",
    "build_initial_state",
    "build_request_context",
]
