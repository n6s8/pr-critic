"""
Critic agents score review candidates and decide whether the branch path is
necessary after the initial review.
"""
from __future__ import annotations

import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.errors import LLMRateLimitError
from backend.graph.state import CandidateScore, CriticAgentInput, CriticAgentOutput
from backend.observability.logger import log_end, log_error, log_routing, log_start, log_structured
from backend.security import mask_pii
from backend.utils.diff import SMART_CRITIC_TOKEN_BUDGET, build_reasoning_diff_packet
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.critic.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """You are evaluating the quality of a code review.

Score the review from 0 to 10 across:
- Usefulness
- Coverage
- False-positive control
- Clarity

Respond only with valid JSON:
{"score": 0.0, "rationale": "one sentence", "issues_identified": ["issue"]}"""


def _is_fallback_candidate(candidate: dict[str, str]) -> bool:
    return candidate.get("strategy", "").startswith("fallback_")


def _is_large_pr_partial_candidate(candidate: dict[str, str]) -> bool:
    return candidate.get("strategy") == "large_pr_partial"


def _parse(content: str) -> tuple[float, str, list[str]]:
    try:
        data = json.loads(content.strip())
        return (
            float(data.get("score", 5.0)),
            str(data.get("rationale", "")),
            [str(issue) for issue in data.get("issues_identified", [])],
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    score_match = re.search(r'"score"\s*:\s*(\d+(?:\.\d+)?)', content)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]+)"', content)
    score = float(score_match.group(1)) if score_match else 5.0
    rationale = rationale_match.group(1) if rationale_match else ""
    return score, rationale, []


def _pending_indexes(candidate_count: int, scores: list[CandidateScore]) -> list[int]:
    scored_indexes = {score["candidate_index"] for score in scores}
    return [index for index in range(candidate_count) if index not in scored_indexes]


def _score_candidate(index: int, review: str, strategy: str, diff: str, *, llm_agent: str) -> CandidateScore:
    diff_excerpt = build_reasoning_diff_packet(
        diff,
        token_budget=SMART_CRITIC_TOKEN_BUDGET,
        max_files=6,
        max_chunks=2,
        max_lines_per_chunk=80,
        max_chars_per_chunk=1000,
    ).content
    prompt = f"""## Diff
```diff
{mask_pii(diff_excerpt)}
```

## Review To Evaluate
{review}

Return the JSON score."""

    response = invoke_llm(
        _llm,
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)],
        agent=llm_agent,
    )
    score, rationale, issues_identified = _parse(response.content)
    return {
        "candidate_index": index,
        "strategy": strategy,
        "score": max(0.0, min(10.0, score)),
        "rationale": rationale,
        "issues_identified": issues_identified,
    }


def _run_critic(
    state: CriticAgentInput,
    *,
    set_branch_taken: bool,
    trace_agent: str,
) -> CriticAgentOutput:
    started_at = time.perf_counter()
    candidates = list(state.get("candidates", []))
    scores = list(state.get("scores", []))
    trace = list(state.get("trace", []))
    pending_indexes = _pending_indexes(len(candidates), scores)
    start_event = log_start(
        trace_agent,
        {
            "candidate_count": len(candidates),
            "pending_indexes": pending_indexes,
            "branch_budget_available": bool(state.get("branch_budget_available", True)),
            "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
            "filtered_diff_used": True,
        },
    )

    if not candidates:
        error_event = log_error(trace_agent, "No candidates to evaluate")
        result: CriticAgentOutput = {
            "scores": scores,
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": "no_candidates",
            "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
            "branch_budget_available": bool(state.get("branch_budget_available", True)),
            "review_plan": state.get("review_plan", {}),
            "safety_flags": state.get("safety_flags", {}),
            "agent_messages": state.get("agent_messages", []),
            "trace": trace + [start_event, error_event],
        }
        if set_branch_taken:
            result["branch_taken"] = False
        return result

    new_scores: list[CandidateScore] = []
    rate_limited = bool(state.get("rate_limited", False))
    for index in pending_indexes:
        candidate = candidates[index]
        if state.get("large_pr_mode", False) and _is_large_pr_partial_candidate(candidate):
            new_scores.append({
                "candidate_index": index,
                "strategy": candidate["strategy"],
                "score": 6.0,
                "rationale": (
                    "Large PR partial-analysis candidate is intentionally conservative: "
                    "it reports scoped coverage instead of inventing findings."
                ),
                "issues_identified": [],
            })
            continue
        if rate_limited or _is_fallback_candidate(candidate):
            new_scores.append({
                "candidate_index": index,
                "strategy": candidate["strategy"],
                "score": 0.0,
                "rationale": (
                    "LLM unavailable due to rate limit"
                    if candidate["strategy"] == "fallback_rate_limited" or rate_limited
                    else "Review generation unavailable"
                ),
                "issues_identified": [],
            })
            continue
        try:
            new_scores.append(
                _score_candidate(
                    index,
                    candidate["review"],
                    candidate["strategy"],
                    state.get("pr_diff", ""),
                    llm_agent=trace_agent,
                )
            )
        except LLMRateLimitError as exc:
            rate_limited = True
            log_structured(
                "WARNING",
                "critic_rate_limited",
                agent=trace_agent,
                retry_after_seconds=exc.retry_after_seconds,
                rate_limited=True,
            )
            trace.append(log_error(trace_agent, f"Rate limited while scoring candidate {index}: {exc}"))
            new_scores.append({
                "candidate_index": index,
                "strategy": candidate["strategy"],
                "score": 0.0,
                "rationale": "LLM unavailable due to rate limit",
                "issues_identified": [],
            })
        except Exception as exc:
            trace.append(log_error(trace_agent, f"Failed to score candidate {index}: {exc}"))
            new_scores.append({
                "candidate_index": index,
                "strategy": candidate["strategy"],
                "score": 0.0,
                "rationale": f"Critic failed: {exc}",
                "issues_identified": [],
            })

    updated_scores = sorted(scores + new_scores, key=lambda item: item["candidate_index"])
    branch_taken = state.get("branch_taken", False)
    branch_skipped_reason = str(state.get("branch_skipped_reason", ""))
    branch_budget_available = bool(state.get("branch_budget_available", True))
    routing_event = None
    if set_branch_taken:
        threshold = settings.thresholds.branch_score_threshold
        initial_score = next((score for score in updated_scores if score["candidate_index"] == 0), None)
        initial_candidate = candidates[0] if candidates else None
        if rate_limited:
            branch_taken = False
            branch_skipped_reason = "rate_limited"
        elif state.get("large_pr_mode", False):
            branch_taken = False
            branch_skipped_reason = "large_pr_mode"
        elif not branch_budget_available:
            branch_taken = False
            branch_skipped_reason = "token_budget"
        elif initial_candidate and _is_fallback_candidate(initial_candidate):
            branch_taken = False
            branch_skipped_reason = (
                "review_unavailable"
                if initial_candidate.get("strategy") == "fallback_unavailable"
                else initial_candidate.get("strategy", "fallback")
            )
        else:
            branch_taken = bool(initial_score and initial_score["score"] < threshold)
            branch_skipped_reason = "" if branch_taken else "threshold_met"
        routing_event = log_routing(
            "branch" if branch_taken else "select",
            (
                f"score={initial_score['score'] if initial_score else 'n/a'}, threshold={threshold}, "
                f"branch_skipped_reason={branch_skipped_reason or 'none'}"
            ),
        )

    end_event = log_end(
        trace_agent,
        {
            "scored_indexes": [score["candidate_index"] for score in new_scores],
            "scores": {score["candidate_index"]: score["score"] for score in updated_scores},
            "branch_taken": branch_taken,
            "rate_limited": rate_limited,
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "branch_skipped_reason": branch_skipped_reason,
            "branch_budget_available": branch_budget_available,
            "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
            "filtered_diff_used": True,
        },
        (time.perf_counter() - started_at) * 1000,
    )
    next_trace = trace + [start_event, end_event]
    if routing_event is not None:
        next_trace.append(routing_event)

    result: CriticAgentOutput = {
        "scores": updated_scores,
        "rate_limited": rate_limited,
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": branch_skipped_reason,
        "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
        "branch_budget_available": branch_budget_available,
        "review_plan": state.get("review_plan", {}),
        "safety_flags": state.get("safety_flags", {}),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": trace_agent,
                "artifact_type": "CriticReport",
                "summary": {
                    "scored_indexes": [score["candidate_index"] for score in new_scores],
                    "branch_taken": branch_taken,
                    "branch_skipped_reason": branch_skipped_reason,
                },
            }
        ],
        "trace": next_trace,
    }
    if set_branch_taken:
        result["branch_taken"] = branch_taken
    return result


def critic_agent(state: CriticAgentInput) -> CriticAgentOutput:
    return _run_critic(state, set_branch_taken=True, trace_agent="critic_initial")


def branch_critic_agent(state: CriticAgentInput) -> CriticAgentOutput:
    return _run_critic(state, set_branch_taken=False, trace_agent="critic_branch")
