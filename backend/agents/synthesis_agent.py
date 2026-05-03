from __future__ import annotations

import time

from backend.graph.state import PRCriticState
from backend.observability.logger import log_end, log_start


def synthesis_agent(state: PRCriticState) -> dict:
    started_at = time.perf_counter()
    trace = list(state.get("trace", []))
    candidate_grounded = state.get("candidate_grounded_issues", {})
    grounded_total = sum(len(items) for items in candidate_grounded.values())
    retrieval_sources = list(state.get("retrieval_sources", []))
    start_event = log_start(
        "synthesis_agent",
        {
            "candidate_count": len(state.get("candidates", [])),
            "grounded_issue_count": grounded_total,
            "retrieval_sources": retrieval_sources,
        },
    )
    report = {
        "grounded_issue_count": grounded_total,
        "retrieval_sources": retrieval_sources,
        "confidence": "high" if grounded_total and retrieval_sources else ("medium" if grounded_total else "high"),
        "limitations": [
            "Only changed lines and selected diff chunks are reviewed.",
            "Issues without changed-line evidence are removed before final selection.",
        ],
    }
    end_event = log_end(
        "synthesis_agent",
        report,
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "synthesis_report": report,
        "rate_limited": bool(state.get("rate_limited", False)),
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
        "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
        "branch_budget_available": bool(state.get("branch_budget_available", True)),
        "safety_flags": state.get("safety_flags", {}),
        "review_plan": state.get("review_plan", {}),
        "candidate_grounded_issues": candidate_grounded,
        "grounded_issues": state.get("grounded_issues", []),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": "synthesis_agent",
                "artifact_type": "FinalDecision",
                "summary": report,
            }
        ],
        "trace": trace + [start_event, end_event],
    }
