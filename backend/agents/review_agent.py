"""
Review agent responsible for the initial balanced review candidate.

The agent consumes the retrieved context and a prompt-safe diff excerpt, then
adds a single candidate to state.
"""
from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.errors import LLMRateLimitError
from backend.graph.state import ReviewAgentInput, ReviewAgentOutput, ReviewCandidate
from backend.observability.logger import log_end, log_error, log_start, log_structured
from backend.security import mask_pii
from backend.utils.cache import TTLCache, build_cache_key
from backend.utils.diff import (
    SMART_BRANCH_TOKEN_BUDGET,
    SMART_TOTAL_INPUT_TOKEN_BUDGET,
    build_llm_diff_packet,
    estimate_tokens,
)
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.review.groq_kwargs(api_key=settings.groq_api_key))
_REVIEW_CACHE: TTLCache[tuple[str, list[str], int, int]] = TTLCache(
    "review_candidates",
    settings.caches.pr_ttl_seconds,
    max_size=128,
)

_SYSTEM = """You are a senior software engineer performing a precise code review.

Rules:
1. Analyze only the code visible in the provided diff.
2. Do not comment on code that is not present in the diff.
3. Do not invent issues.
4. Use the provided programming language, do not default to Python.
5. Reference concrete files, lines, or snippets when you raise issues.
6. When possible, use a canonical issue type in snake_case.
7. Every issue must include changed-line evidence and a source id when retrieval guidance supports it.

Use this structure exactly:
## Summary
One or two sentences describing what the change does.

## Issues Found
- [SEVERITY] [ISSUE_TYPE] [FILE:LINE if visible] Description
- Include "(evidence: `changed code`; source: source_id)" when available.
- If the issue type is uncertain, use [unknown].

## Suggestions
Concrete improvements. Keep them specific to the diff.

## Verdict
APPROVE / REQUEST_CHANGES / COMMENT
Include a one-sentence justification."""

_REVIEW_PROMPT_OVERHEAD_TOKENS = 400


def _empty_candidate(review_text: str) -> ReviewCandidate:
    return {
        "id": "initial-0",
        "review": review_text,
        "strategy": "initial",
    }


def _fallback_candidate(index: int, *, review_text: str, strategy: str) -> ReviewCandidate:
    return {
        "id": f"{strategy}-{index}",
        "review": review_text,
        "strategy": strategy,
    }


def _large_pr_partial_review(
    *,
    metadata: dict,
    language: str,
    diff_packet,
    files_str: str,
) -> str:
    reviewed_files = ", ".join(diff_packet.included_files) or files_str
    omitted_note = (
        f"{diff_packet.omitted_chunks} lower-priority diff chunk(s) were omitted by the token budget."
        if diff_packet.omitted_chunks
        else "No additional diff chunks were omitted by the smart filter."
    )
    title = metadata.get("title", "N/A")
    return f"""## Summary
Large PR partial analysis mode is active for "{title}". The diff is too large for an exhaustive LLM review, so the system inspected the highest-priority changed chunks for {language}.

## Issues Found
None.

## Suggestions
- Split this PR into smaller reviewable changes before merge.
- Re-run the review on smaller PRs or targeted files for line-level findings.
- Treat this result as partial coverage, not approval of the full PR.

## Grounding
0 issue(s) retained because no changed-line evidence has been validated in large PR mode.
Reviewed prioritized files: {reviewed_files}
{omitted_note}

## Verdict
COMMENT
Partial analysis only; do not treat this result as full approval."""


def _build_chunk_prompt(
    *,
    metadata: dict,
    language: str,
    files_str: str,
    retrieved_context: str,
    repo_context: str,
    diff_content: str,
    review_plan: dict,
    chunk_index: int,
    total_chunks: int,
) -> str:
    return f"""## PR Information
Title: {metadata.get('title', 'N/A')}
Author: {metadata.get('author', 'N/A')}
Language: {language}
Files changed: {files_str}
Branch: {metadata.get('head_branch', 'N/A')} -> {metadata.get('base_branch', 'main')}

## Retrieval Guidance
{retrieved_context}

## Repository Signals
{repo_context}

## Review Plan
Focus: {review_plan.get('focus', 'balanced')}
Rationale: {review_plan.get('rationale', 'No explicit plan.')}
Expected issue types: {', '.join(review_plan.get('expected_issue_types', [])) or 'none'}

## Filtered Diff Scope
Selected chunk(s): {total_chunks}
Packet index: {chunk_index + 1}

## Diff To Review
```diff
{diff_content}
```

Write the review for this filtered diff packet now."""


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


def review_agent(state: ReviewAgentInput) -> ReviewAgentOutput:
    started_at = time.perf_counter()
    diff = state.get("pr_diff", "")
    metadata = state.get("pr_metadata", {})
    language = metadata.get("language", "Unknown")
    trace = list(state.get("trace", []))
    start_event = log_start(
        "review_agent",
        {
            "diff_length": len(diff),
            "language": language,
            "retrieval_sources": state.get("retrieval_sources", []),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signal_checkout": state.get("repo_signals", {}).get("checkout_status", "unknown"),
            "repo_signal_lint": state.get("repo_signals", {}).get("lint_status", "unknown"),
        },
    )

    if state.get("rate_limited", False):
        fallback = _fallback_candidate(
            len(state.get("candidates", [])),
            review_text="LLM unavailable due to rate limit",
            strategy="fallback_rate_limited",
        )
        end_event = log_end(
            "review_agent",
            {
                "strategy": fallback["strategy"],
                "fallback_used": True,
                "rate_limited": True,
                "reason": "rate_limited_state",
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [fallback],
            "rate_limited": True,
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": "rate_limited",
            "llm_input_tokens": 0,
            "branch_budget_available": False,
            "trace": trace + [start_event, end_event],
        }

    if not diff.strip():
        review_text = "No diff content available for review."
        end_event = log_end(
            "review_agent",
            {"strategy": "initial", "empty": True},
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [_empty_candidate(review_text)],
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "llm_input_tokens": int(state.get("llm_input_tokens", 0)),
            "branch_budget_available": bool(state.get("branch_budget_available", True)),
            "trace": trace + [start_event, end_event],
        }

    try:
        files_str = ", ".join(metadata.get("files_changed", [])) or "unknown"
        request_cache_key = str(state.get("request_cache_key", ""))
        diff_packet = build_llm_diff_packet(diff)
        if state.get("large_pr_mode", False):
            review_text = _large_pr_partial_review(
                metadata=metadata,
                language=language,
                diff_packet=diff_packet,
                files_str=files_str,
            )
            candidate: ReviewCandidate = {
                "id": f"large-pr-partial-{len(state.get('candidates', []))}",
                "review": review_text,
                "strategy": "large_pr_partial",
            }
            end_event = log_end(
                "review_agent",
                {
                    "strategy": "large_pr_partial",
                    "language": language,
                    "review_length": len(review_text),
                    "estimated_output_tokens": estimate_tokens(review_text),
                    "chunk_count": diff_packet.selected_chunks,
                    "included_files": diff_packet.included_files,
                    "filtered_diff_used": True,
                    "selected_chunks": diff_packet.selected_chunks,
                    "omitted_chunks": diff_packet.omitted_chunks,
                    "estimated_input_tokens": diff_packet.estimated_tokens,
                    "diff_tokens": diff_packet.estimated_tokens,
                    "large_pr_partial": True,
                    "cache_hit": False,
                },
                (time.perf_counter() - started_at) * 1000,
            )
            return {
                "candidates": state.get("candidates", []) + [candidate],
                "rate_limited": False,
                "large_pr_mode": True,
                "repo_signals": state.get("repo_signals"),
                "request_cache_key": request_cache_key,
                "branch_skipped_reason": "large_pr_mode",
                "llm_input_tokens": diff_packet.estimated_tokens,
                "branch_budget_available": False,
                "review_plan": state.get("review_plan", {}),
                "safety_flags": state.get("safety_flags", {}),
                "agent_messages": list(state.get("agent_messages", [])) + [
                    {
                        "agent": "review_agent",
                        "artifact_type": "ReviewCandidate",
                        "summary": {
                            "strategy": "large_pr_partial",
                            "included_files": diff_packet.included_files,
                            "omitted_chunks": diff_packet.omitted_chunks,
                            "estimated_input_tokens": diff_packet.estimated_tokens,
                            "estimated_output_tokens": estimate_tokens(review_text),
                        },
                    }
                ],
                "trace": trace + [start_event, end_event],
            }
        context_budget = max(
            120,
            SMART_TOTAL_INPUT_TOKEN_BUDGET - _REVIEW_PROMPT_OVERHEAD_TOKENS - diff_packet.estimated_tokens,
        )
        compact_context = _trim_to_token_budget(
            mask_pii(state.get("retrieved_context", "")),
            max_tokens=min(260, context_budget),
        )
        repo_signal_summary = _trim_to_token_budget(
            mask_pii(state.get("repo_signals", {}).get("summary", "No repository signals available.")),
            max_tokens=140,
        ) or "No repository signals available."
        total_input_tokens = (
            diff_packet.estimated_tokens
            + estimate_tokens(compact_context)
            + estimate_tokens(repo_signal_summary)
            + _REVIEW_PROMPT_OVERHEAD_TOKENS
        )
        branch_budget_available = total_input_tokens <= SMART_BRANCH_TOKEN_BUDGET
        review_cache_key = build_cache_key(
            request_cache_key or diff_packet.content,
            language,
            compact_context,
            repo_signal_summary,
            "initial_review_v3",
        )
        cache_hit, cached_review = _REVIEW_CACHE.get(review_cache_key)
        if cache_hit and cached_review is not None:
            review_text, chunk_files, input_tokens, selected_chunks = cached_review
            candidate: ReviewCandidate = {
                "id": f"initial-{len(state.get('candidates', []))}",
                "review": review_text,
                "strategy": "initial",
            }
            end_event = log_end(
                "review_agent",
                {
                    "strategy": "initial",
                    "language": language,
                    "review_length": len(review_text),
                    "chunk_count": selected_chunks,
                    "included_files": chunk_files,
                    "filtered_diff_used": True,
                    "selected_chunks": selected_chunks,
                    "estimated_input_tokens": input_tokens,
                    "cache_hit": True,
                    "repo_signals_used": bool(repo_signal_summary),
                },
                (time.perf_counter() - started_at) * 1000,
            )
            return {
                "candidates": state.get("candidates", []) + [candidate],
                "rate_limited": False,
                "large_pr_mode": bool(state.get("large_pr_mode", False)),
                "repo_signals": state.get("repo_signals"),
                "request_cache_key": request_cache_key,
                "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
                "llm_input_tokens": input_tokens,
                "branch_budget_available": input_tokens <= SMART_BRANCH_TOKEN_BUDGET,
                "trace": trace + [start_event, end_event],
            }
        selected_files_str = ", ".join(diff_packet.included_files) or files_str
        prompt = _build_chunk_prompt(
            metadata=metadata,
            language=language,
            files_str=selected_files_str,
            retrieved_context=compact_context,
            repo_context=repo_signal_summary,
            diff_content=mask_pii(diff_packet.content),
            review_plan=state.get("review_plan", {}),
            chunk_index=0,
            total_chunks=max(1, diff_packet.selected_chunks),
        )
        response = invoke_llm(
            _llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)],
            agent="review_agent",
        )
        review_text = response.content
        candidate: ReviewCandidate = {
            "id": f"initial-{len(state.get('candidates', []))}",
            "review": review_text,
            "strategy": "initial",
        }
        _REVIEW_CACHE.set(
            review_cache_key,
            (review_text, diff_packet.included_files, total_input_tokens, diff_packet.selected_chunks),
        )
        end_event = log_end(
            "review_agent",
            {
                "strategy": "initial",
                "language": language,
                "review_length": len(review_text),
                "estimated_output_tokens": estimate_tokens(review_text),
                "chunk_count": diff_packet.selected_chunks,
                "included_files": diff_packet.included_files,
                "filtered_diff_used": True,
                "selected_chunks": diff_packet.selected_chunks,
                "estimated_input_tokens": total_input_tokens,
                "diff_tokens": diff_packet.estimated_tokens,
                "rag_tokens": estimate_tokens(compact_context),
                "repo_signal_tokens": estimate_tokens(repo_signal_summary),
                "repo_signals_used": bool(repo_signal_summary),
                "branch_budget_available": branch_budget_available,
                "cache_hit": False,
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [candidate],
            "rate_limited": False,
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": request_cache_key,
            "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
            "llm_input_tokens": total_input_tokens,
            "branch_budget_available": branch_budget_available,
            "review_plan": state.get("review_plan", {}),
            "safety_flags": state.get("safety_flags", {}),
            "agent_messages": list(state.get("agent_messages", [])) + [
                {
                    "agent": "review_agent",
                    "artifact_type": "ReviewCandidate",
                    "summary": {
                        "strategy": "initial",
                        "included_files": diff_packet.included_files,
                        "estimated_input_tokens": total_input_tokens,
                        "estimated_output_tokens": estimate_tokens(review_text),
                    },
                }
            ],
            "trace": trace + [start_event, end_event],
        }
    except LLMRateLimitError as exc:
        log_structured(
            "WARNING",
            "review_agent_rate_limited",
            agent="review_agent",
            retry_after_seconds=exc.retry_after_seconds,
            rate_limited=True,
        )
        fallback = _fallback_candidate(
            len(state.get("candidates", [])),
            review_text="LLM unavailable due to rate limit",
            strategy="fallback_rate_limited",
        )
        end_event = log_end(
            "review_agent",
            {
                "strategy": fallback["strategy"],
                "fallback_used": True,
                "rate_limited": True,
                "reason": exc.code,
                "retry_after_seconds": exc.retry_after_seconds,
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [fallback],
            "rate_limited": True,
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": "rate_limited",
            "llm_input_tokens": 0,
            "branch_budget_available": False,
            "trace": trace + [start_event, end_event],
        }
    except Exception as exc:
        fallback = _fallback_candidate(
            len(state.get("candidates", [])),
            review_text="Review generation unavailable",
            strategy="fallback_unavailable",
        )
        error_event = log_error("review_agent", str(exc))
        return {
            "candidates": state.get("candidates", []) + [fallback],
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": bool(state.get("large_pr_mode", False)),
            "repo_signals": state.get("repo_signals"),
            "request_cache_key": str(state.get("request_cache_key", "")),
            "branch_skipped_reason": "review_unavailable",
            "llm_input_tokens": 0,
            "branch_budget_available": False,
            "trace": trace + [start_event, error_event],
        }
