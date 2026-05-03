"""
Branch agent responsible for creating genuine alternative review candidates
when the initial review underperforms the branch threshold.
"""
from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.errors import LLMRateLimitError
from backend.graph.state import BranchAgentInput, BranchAgentOutput, CandidateScore, ReviewCandidate
from backend.observability.logger import log_end, log_error, log_start, log_structured
from backend.security import mask_pii
from backend.utils.diff import SMART_TOTAL_INPUT_TOKEN_BUDGET, build_llm_diff_packet, estimate_tokens
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.branch.groq_kwargs(api_key=settings.groq_api_key))

_BASE_RULES = """Analyze only the code in the provided diff.
Do not invent missing code or comment on files outside the diff.
Use the supplied programming language and keep the review grounded in the change itself.
When possible, emit issue types in snake_case using this issue format:
- [SEVERITY] [ISSUE_TYPE] [FILE:LINE if visible] Description"""

_ALL_STRATEGIES = [
    {
        "name": "security_focus",
        "languages": ["*"],
        "prompt": f"""{_BASE_RULES}

You are a security-focused code reviewer.
Focus on vulnerabilities visible in the diff: access control, injection,
hardcoded secrets, insecure deserialization, weak crypto, XSS, CSRF,
privilege escalation, and unsafe shell execution.

Use this structure:
## Summary
## Issues Found
## Suggestions
## Verdict""",
    },
    {
        "name": "correctness_focus",
        "languages": ["*"],
        "prompt": f"""{_BASE_RULES}

You are a correctness-focused code reviewer.
Focus on logic errors, edge cases, null handling, incorrect assumptions,
error handling, and behavior regressions visible in the diff.

Use this structure:
## Summary
## Issues Found
## Suggestions
## Verdict""",
    },
    {
        "name": "typescript_idioms",
        "languages": ["TypeScript", "JavaScript"],
        "prompt": f"""{_BASE_RULES}

You are a TypeScript and React reviewer.
Focus on type safety, hooks correctness, async patterns, null safety,
unsanitized HTML rendering, and browser-side security issues visible in the diff.

Use this structure:
## Summary
## Issues Found
## Suggestions
## Verdict""",
    },
    {
        "name": "python_idioms",
        "languages": ["Python"],
        "prompt": f"""{_BASE_RULES}

You are a Python reviewer.
Focus on Pythonic patterns, exception handling, type annotations,
security-sensitive library usage, and maintainability issues visible in the diff.

Use this structure:
## Summary
## Issues Found
## Suggestions
## Verdict""",
    },
]

_BRANCH_REVIEW_TOKEN_BUDGET = 750
_BRANCH_PROMPT_OVERHEAD_TOKENS = 550


def _strategies_for_language(language: str) -> list[dict]:
    language_specific = next(
        (
            strategy for strategy in _ALL_STRATEGIES
            if language in strategy["languages"] and strategy["languages"] != ["*"]
        ),
        None,
    )
    security = next(strategy for strategy in _ALL_STRATEGIES if strategy["name"] == "security_focus")
    fallback = next(strategy for strategy in _ALL_STRATEGIES if strategy["name"] == "correctness_focus")

    selected = [security, language_specific or fallback]
    seen: set[str] = set()
    ordered: list[dict] = []
    for strategy in selected:
        if strategy["name"] not in seen:
            seen.add(strategy["name"])
            ordered.append(strategy)
    return ordered


def _score_lookup(scores: list[CandidateScore]) -> dict[int, CandidateScore]:
    return {score["candidate_index"]: score for score in scores}


def _trim_to_token_budget(text: str, *, max_tokens: int) -> str:
    normalized = text.strip()
    if not normalized or max_tokens <= 0:
        return ""
    if estimate_tokens(normalized) <= max_tokens:
        return normalized

    kept_lines: list[str] = []
    for line in normalized.splitlines():
        candidate = "\n".join(kept_lines + [line]).strip()
        if kept_lines and estimate_tokens(candidate) > max_tokens:
            break
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def branch_agent(state: BranchAgentInput) -> BranchAgentOutput:
    started_at = time.perf_counter()
    diff = state.get("pr_diff", "")
    metadata = state.get("pr_metadata", {})
    language = metadata.get("language", "Unknown")
    existing_candidates = list(state.get("candidates", []))
    existing_scores = _score_lookup(state.get("scores", []))
    trace = list(state.get("trace", []))
    strategies = _strategies_for_language(language)[: settings.thresholds.max_branch_alternatives]
    start_event = log_start(
        "branch_agent",
        {
            "language": language,
            "strategy_names": [strategy["name"] for strategy in strategies],
            "existing_candidates": len(existing_candidates),
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "branch_budget_available": bool(state.get("branch_budget_available", True)),
        },
    )

    if state.get("rate_limited", False) or state.get("large_pr_mode", False) or not state.get("branch_budget_available", True):
        reason = (
            "rate_limited"
            if state.get("rate_limited", False)
            else ("large_pr_mode" if state.get("large_pr_mode", False) else "token_budget")
        )
        end_event = log_end(
            "branch_agent",
            {
                "generated": 0,
                "branch_skipped_reason": reason,
                "rate_limited": bool(state.get("rate_limited", False)),
                "large_pr_mode": bool(state.get("large_pr_mode", False)),
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": existing_candidates,
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": reason,
            "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
            "branch_budget_available": bool(state.get("branch_budget_available", True)),
            "review_plan": state.get("review_plan", {}),
            "safety_flags": state.get("safety_flags", {}),
            "agent_messages": state.get("agent_messages", []),
            "trace": trace + [start_event, end_event],
        }

    initial_candidate = existing_candidates[0] if existing_candidates else None
    initial_score = existing_scores.get(0)
    files_str = ", ".join(metadata.get("files_changed", [])) or "unknown"
    diff_packet = build_llm_diff_packet(
        diff,
        max_chunks=3,
        max_chars_per_chunk=1000,
        max_lines_per_chunk=80,
        token_budget=_BRANCH_REVIEW_TOKEN_BUDGET,
    )
    compact_context = _trim_to_token_budget(state.get("retrieved_context", ""), max_tokens=160)
    prior_review = _trim_to_token_budget(
        initial_candidate["review"] if initial_candidate else "No prior review available.",
        max_tokens=260,
    )
    new_candidates: list[ReviewCandidate] = []

    for offset, strategy in enumerate(strategies, start=len(existing_candidates)):
        try:
            critique = ""
            if initial_score:
                critique = (
                    f"Initial review score: {initial_score['score']:.1f}\n"
                    f"Critic rationale: {initial_score['rationale']}\n"
                    f"Critic identified: {', '.join(initial_score['issues_identified']) or 'none'}"
                )
            compact_critique = _trim_to_token_budget(critique, max_tokens=120)
            total_input_tokens = (
                diff_packet.estimated_tokens
                + estimate_tokens(compact_context)
                + estimate_tokens(prior_review)
                + estimate_tokens(compact_critique)
                + _BRANCH_PROMPT_OVERHEAD_TOKENS
            )
            if total_input_tokens > SMART_TOTAL_INPUT_TOKEN_BUDGET:
                trace.append(log_error("branch_agent", f"strategy '{strategy['name']}' skipped: token budget exceeded"))
                continue

            prompt = f"""## PR Information
Title: {metadata.get('title', 'N/A')}
Language: {language}
Files changed: {', '.join(diff_packet.included_files) or files_str}

## Retrieved Guidance
{mask_pii(compact_context)}

## Review Plan
Focus: {state.get('review_plan', {}).get('focus', 'balanced')}
Expected issue types: {', '.join(state.get('review_plan', {}).get('expected_issue_types', [])) or 'none'}

## Prior Review To Improve
{prior_review}

## Why Another Strategy Is Needed
{compact_critique or 'The prior review did not meet the branch threshold.'}

## Filtered Diff Scope
Selected chunk(s): {diff_packet.selected_chunks}

## Diff To Review
```diff
{mask_pii(diff_packet.content)}
```

Produce a materially different review using your assigned strategy."""
            response = invoke_llm(
                _llm,
                [SystemMessage(content=strategy["prompt"]), HumanMessage(content=prompt)],
                agent="branch_agent",
                attempts=1,
            )
            new_candidates.append({
                "id": f"{strategy['name']}-{offset}",
                "review": response.content,
                "strategy": strategy["name"],
            })
        except LLMRateLimitError as exc:
            log_structured(
                "WARNING",
                "branch_agent_rate_limited",
                agent="branch_agent",
                retry_after_seconds=exc.retry_after_seconds,
                rate_limited=True,
            )
            trace.append(log_error("branch_agent", f"rate limited while running '{strategy['name']}': {exc}"))
            end_event = log_end(
                "branch_agent",
                {
                    "language": language,
                    "strategies_run": [strategy["name"] for strategy in strategies],
                    "generated": len(new_candidates),
                    "chunk_count": diff_packet.selected_chunks,
                    "included_files": diff_packet.included_files,
                    "rate_limited": True,
                    "branch_skipped_reason": "rate_limited",
                },
                (time.perf_counter() - started_at) * 1000,
            )
            return {
                "candidates": existing_candidates + new_candidates,
                "rate_limited": True,
                "large_pr_mode": bool(state.get("large_pr_mode", False)),
                "repo_signals": state.get("repo_signals"),
                "request_cache_key": str(state.get("request_cache_key", "")),
                "branch_skipped_reason": "rate_limited",
                "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
                "branch_budget_available": False,
                "review_plan": state.get("review_plan", {}),
                "safety_flags": state.get("safety_flags", {}),
                "agent_messages": state.get("agent_messages", []),
                "trace": trace + [start_event, end_event],
            }
        except Exception as exc:
            trace.append(log_error("branch_agent", f"strategy '{strategy['name']}' failed: {exc}"))

    end_event = log_end(
        "branch_agent",
        {
            "language": language,
            "strategies_run": [strategy["name"] for strategy in strategies],
            "generated": len(new_candidates),
            "chunk_count": diff_packet.selected_chunks,
            "included_files": diff_packet.included_files,
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "candidates": existing_candidates + new_candidates,
        "rate_limited": bool(state.get("rate_limited", False)),
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
        "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
        "branch_budget_available": bool(state.get("branch_budget_available", True)),
        "review_plan": state.get("review_plan", {}),
        "safety_flags": state.get("safety_flags", {}),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": "branch_agent",
                "artifact_type": "ReviewCandidate",
                "summary": {
                    "generated": len(new_candidates),
                    "strategies": [candidate["strategy"] for candidate in new_candidates],
                },
            }
        ],
        "trace": trace + [start_event, end_event],
    }
