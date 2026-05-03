"""
Selector agent chooses the best candidate from the scored candidate set.
"""
from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.errors import LLMRateLimitError
from backend.graph.state import CandidateScore, SelectorAgentInput, SelectorAgentOutput
from backend.observability.logger import log_end, log_error, log_start, log_structured
from backend.security import mask_pii
from backend.utils.diff import SMART_SELECTOR_TOKEN_BUDGET, build_reasoning_diff_packet
from backend.utils.grounding import render_grounded_review
from backend.utils.issues import file_paths_match
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.selector.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """Select the best code review from the candidates below.
Consider review quality, score, and how well the review matches the diff.

Respond only with valid JSON:
{"best_index": 0, "rationale": "one sentence"}"""


def _score_lookup(scores: list[CandidateScore]) -> dict[int, CandidateScore]:
    return {score["candidate_index"]: score for score in scores}


def _build_selector_reason(
    candidates: list[dict[str, str]],
    score_lookup: dict[int, CandidateScore],
    selected_index: int,
    raw_rationale: str,
) -> str:
    if len(candidates) == 1:
        if candidates[0].get("strategy") == "fallback_rate_limited":
            return "LLM unavailable due to rate limit; returning the fallback candidate."
        if candidates[0].get("strategy", "").startswith("fallback_"):
            return "Review generation degraded; returning the fallback candidate."
        return "Selected the only candidate returned by the pipeline."

    selected_candidate = candidates[selected_index]
    selected_score = float(score_lookup.get(selected_index, {}).get("score", 0.0))
    baseline_score = float(score_lookup.get(0, {}).get("score", selected_score))
    selected_issues = score_lookup.get(selected_index, {}).get("issues_identified", [])
    baseline_issues = score_lookup.get(0, {}).get("issues_identified", [])
    parts: list[str] = []

    if selected_index != 0:
        if selected_score > baseline_score:
            parts.append(
                f"Selected {selected_candidate['strategy']} because it scored highest "
                f"({selected_score:.1f} vs {baseline_score:.1f} for the initial review)."
            )
        else:
            parts.append(
                f"Selected {selected_candidate['strategy']} because it matched the best score "
                f"while offering a different review strategy."
            )
    else:
        parts.append(
            f"Selected {selected_candidate['strategy']} because it remained the strongest "
            f"candidate at {selected_score:.1f}."
        )

    if len(selected_issues) > len(baseline_issues):
        parts.append(
            f"It covered more concrete issues ({len(selected_issues)} vs {len(baseline_issues)})."
        )
    elif selected_index != 0 and selected_issues:
        parts.append("It preserved issue coverage without adding weaker alternatives.")

    cleaned_rationale = raw_rationale.strip().rstrip(".")
    if cleaned_rationale:
        summary = " ".join(parts).lower()
        if cleaned_rationale.lower() not in summary:
            parts.append(f"{cleaned_rationale[0].upper()}{cleaned_rationale[1:]}.")

    return " ".join(parts)


def _compute_branch_improvement(
    score_lookup: dict[int, CandidateScore],
    selected_index: int | None,
    branch_taken: bool,
) -> float | None:
    if not branch_taken or selected_index is None:
        return None

    initial_score = score_lookup.get(0)
    selected_score = score_lookup.get(selected_index)
    if not initial_score or not selected_score:
        return None

    return round(float(selected_score["score"]) - float(initial_score["score"]), 2)


def _dedupe_grounded_issues(candidate_grounded: dict[str, list[dict]]) -> list[dict]:
    deduped: list[dict] = []
    for issues in candidate_grounded.values():
        for issue in issues:
            issue_type = str(issue.get("issue_type", "unknown"))
            file_path = str(issue.get("file", "unknown"))
            if any(
                issue_type == str(existing.get("issue_type", "unknown"))
                and file_paths_match(file_path, str(existing.get("file", "unknown")))
                for existing in deduped
            ):
                continue
            deduped.append(issue)
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(
        deduped,
        key=lambda issue: (
            severity_rank.get(str(issue.get("severity", "info")), 3),
            str(issue.get("file", "")),
            int(issue.get("line") or 0),
        ),
    )


def _rerank(state: SelectorAgentInput) -> tuple[int, str]:
    candidates = state.get("candidates", [])
    score_lookup = _score_lookup(state.get("scores", []))
    diff_excerpt = build_reasoning_diff_packet(
        state.get("pr_diff", ""),
        token_budget=SMART_SELECTOR_TOKEN_BUDGET,
        max_files=6,
        max_chunks=2,
        max_lines_per_chunk=80,
        max_chars_per_chunk=900,
    ).content
    summaries = "\n\n".join(
        (
            f"[{index}] strategy={candidate['strategy']} "
            f"score={score_lookup.get(index, {}).get('score', 0.0):.1f}\n"
            f"critic_rationale={score_lookup.get(index, {}).get('rationale', '')}\n"
            f"{candidate['review'][:500]}"
        )
        for index, candidate in enumerate(candidates)
    )
    prompt = f"""## Diff
```diff
{mask_pii(diff_excerpt)}
```

## Candidates
{summaries}

Return the JSON decision."""
    response = invoke_llm(
        _llm,
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)],
        agent="selector_agent",
    )
    payload = json.loads(response.content.strip())
    best_index = int(payload.get("best_index", 0))
    rationale = str(payload.get("rationale", ""))
    if 0 <= best_index < len(candidates):
        return best_index, rationale
    raise ValueError(f"Selector returned invalid best_index={best_index}")


def selector_agent(state: SelectorAgentInput) -> SelectorAgentOutput:
    started_at = time.perf_counter()
    candidates = state.get("candidates", [])
    scores = state.get("scores", [])
    trace = list(state.get("trace", []))
    start_event = log_start(
        "selector_agent",
        {
            "candidate_count": len(candidates),
            "score_count": len(scores),
            "filtered_diff_used": True,
        },
    )

    if not candidates:
        error_event = log_error("selector_agent", "No candidates")
        return {
            "selected_index": None,
            "selector_reason": "No candidates were produced by the pipeline.",
            "branch_improvement": None,
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "review_plan": state.get("review_plan", {}),
            "safety_flags": state.get("safety_flags", {}),
            "candidate_grounded_issues": state.get("candidate_grounded_issues", {}),
            "grounded_issues": state.get("grounded_issues", []),
            "synthesis_report": state.get("synthesis_report", {}),
            "agent_messages": state.get("agent_messages", []),
            "trace": trace + [start_event, error_event],
        }

    score_lookup = _score_lookup(scores)
    branch_taken = bool(state.get("branch_taken", False))
    rate_limited = bool(state.get("rate_limited", False))
    try:
        if len(candidates) == 1 or rate_limited:
            if candidates[0].get("strategy") == "fallback_rate_limited":
                selected_index, rationale = 0, "LLM unavailable due to rate limit; returning the fallback candidate."
            elif len(candidates) == 1 and candidates[0].get("strategy", "").startswith("fallback_"):
                selected_index, rationale = 0, "Review generation degraded; returning the fallback candidate."
            elif rate_limited:
                selected_index = max(
                    range(len(candidates)),
                    key=lambda index: score_lookup.get(index, {}).get("score", 0.0),
                )
                rationale = "Rate limited: selected the highest scored candidate without reranking."
            else:
                selected_index, rationale = 0, "Selected the only candidate returned by the pipeline."
        else:
            selected_index, rationale = _rerank(state)
    except LLMRateLimitError as exc:
        rate_limited = True
        log_structured(
            "WARNING",
            "selector_rate_limited",
            agent="selector_agent",
            retry_after_seconds=exc.retry_after_seconds,
            rate_limited=True,
        )
        selected_index = max(
            range(len(candidates)),
            key=lambda index: score_lookup.get(index, {}).get("score", 0.0),
        )
        rationale = "Rate limited: selected the highest scored candidate without reranking."
    except Exception as exc:
        log_structured(
            "WARNING",
            "selector_rerank_fallback",
            agent="selector_agent",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        selected_index = max(
            range(len(candidates)),
            key=lambda index: score_lookup.get(index, {}).get("score", 0.0),
        )
        rationale = "Fallback: highest critic score."

    selected_score = score_lookup.get(selected_index, {}).get("score", 0.0)
    selector_reason = _build_selector_reason(candidates, score_lookup, selected_index, rationale)
    branch_improvement = _compute_branch_improvement(score_lookup, selected_index, branch_taken)
    candidate_grounded = state.get("candidate_grounded_issues", {})
    grounded_union = _dedupe_grounded_issues(candidate_grounded) if isinstance(candidate_grounded, dict) else []
    final_candidates = [dict(candidate) for candidate in candidates]
    selected_grounded = (
        grounded_union
        or (candidate_grounded.get(str(selected_index), []) if isinstance(candidate_grounded, dict) else [])
    )
    if selected_grounded:
        final_candidates[selected_index]["review"] = render_grounded_review(
            candidates[selected_index].get("review", ""),
            selected_grounded,
        )
        if grounded_union:
            selector_reason = f"{selector_reason} Synthesized {len(grounded_union)} grounded issue(s) across candidates."
    end_event = log_end(
        "selector_agent",
        {
            "selected_index": selected_index,
            "selected_strategy": candidates[selected_index]["strategy"],
            "selected_score": selected_score,
            "selector_reason": selector_reason,
            "branch_improvement": branch_improvement,
            "rate_limited": rate_limited,
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "filtered_diff_used": True,
            "synthesized_grounded_issues": len(grounded_union),
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "candidates": final_candidates,
        "selected_index": selected_index,
        "selector_reason": selector_reason,
        "branch_improvement": branch_improvement,
        "rate_limited": rate_limited,
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
        "review_plan": state.get("review_plan", {}),
        "safety_flags": state.get("safety_flags", {}),
        "candidate_grounded_issues": candidate_grounded,
        "grounded_issues": selected_grounded,
        "synthesis_report": state.get("synthesis_report", {}),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": "selector_agent",
                "artifact_type": "FinalDecision",
                "summary": {
                    "selected_index": selected_index,
                    "selected_strategy": candidates[selected_index]["strategy"],
                    "selector_reason": selector_reason,
                },
            }
        ],
        "trace": trace + [start_event, end_event],
    }
