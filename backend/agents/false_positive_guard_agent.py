from __future__ import annotations

import time

from backend.graph.state import PRCriticState
from backend.observability.logger import log_end, log_start
from backend.utils.grounding import ground_review_issues, render_grounded_review


def false_positive_guard_agent(state: PRCriticState) -> dict:
    started_at = time.perf_counter()
    trace = list(state.get("trace", []))
    candidates = list(state.get("candidates", []))
    files_changed = list(state.get("pr_metadata", {}).get("files_changed", []))
    review_focus = str(state.get("review_plan", {}).get("focus", "balanced"))
    start_event = log_start(
        "false_positive_guard_agent",
        {
            "candidate_count": len(candidates),
            "review_focus": review_focus,
            "files_changed": files_changed,
        },
    )

    candidate_grounded: dict[str, list[dict]] = {}
    guarded_candidates: list[dict] = []
    removed_total = 0
    retained_total = 0
    for index, candidate in enumerate(candidates):
        grounded = ground_review_issues(
            candidate.get("review", ""),
            diff=state.get("pr_diff", ""),
            files_changed=files_changed,
            retrieval_hits=list(state.get("retrieval_hits", [])),
            review_focus=review_focus,
            candidate_index=index,
        )
        original_issue_count = candidate.get("review", "").count("- [")
        removed_total += max(0, original_issue_count - len(grounded))
        retained_total += len(grounded)
        candidate_grounded[str(index)] = grounded
        guarded = dict(candidate)
        if original_issue_count:
            guarded["review"] = render_grounded_review(candidate.get("review", ""), grounded)
        guarded_candidates.append(guarded)

    selected_index = state.get("selected_index")
    selected_grounded = (
        candidate_grounded.get(str(selected_index), [])
        if selected_index is not None
        else []
    )
    end_event = log_end(
        "false_positive_guard_agent",
        {
            "retained_grounded_issues": retained_total,
            "removed_unsupported_issues": removed_total,
            "citation_validation": "changed_line_required",
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "candidates": guarded_candidates,
        "candidate_grounded_issues": candidate_grounded,
        "grounded_issues": selected_grounded,
        "rate_limited": bool(state.get("rate_limited", False)),
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
        "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
        "branch_budget_available": bool(state.get("branch_budget_available", True)),
        "safety_flags": state.get("safety_flags", {}),
        "review_plan": state.get("review_plan", {}),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": "false_positive_guard_agent",
                "artifact_type": "CriticReport",
                "summary": {
                    "retained_grounded_issues": retained_total,
                    "removed_unsupported_issues": removed_total,
                },
            }
        ],
        "trace": trace + [start_event, end_event],
    }
