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
from backend.graph.state import ReviewAgentInput, ReviewAgentOutput, ReviewCandidate
from backend.observability.logger import log_end, log_error, log_start
from backend.utils.diff import prepare_diff_for_prompt
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.review.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """You are a senior software engineer performing a precise code review.

Rules:
1. Analyze only the code visible in the provided diff.
2. Do not comment on code that is not present in the diff.
3. Do not invent issues.
4. Use the provided programming language, do not default to Python.
5. Reference concrete files, lines, or snippets when you raise issues.

Use this structure exactly:
## Summary
One or two sentences describing what the change does.

## Issues Found
- [SEVERITY] [FILE:LINE if visible] Description

## Suggestions
Concrete improvements. Keep them specific to the diff.

## Verdict
APPROVE / REQUEST_CHANGES / COMMENT
Include a one-sentence justification."""


def _empty_candidate(review_text: str) -> ReviewCandidate:
    return {
        "id": "initial-0",
        "review": review_text,
        "strategy": "initial",
    }


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
        },
    )

    if not diff.strip() or diff.strip().startswith("# ERROR:"):
        review_text = "No diff content available for review."
        if diff.strip().startswith("# ERROR:"):
            review_text = f"{review_text}\n\n{diff}"
        end_event = log_end(
            "review_agent",
            {"strategy": "initial", "empty": True},
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [_empty_candidate(review_text)],
            "trace": trace + [start_event, end_event],
        }

    try:
        diff_selection = prepare_diff_for_prompt(diff, max_chars=4000)
        files_str = ", ".join(metadata.get("files_changed", [])) or "unknown"
        prompt = f"""## PR Information
Title: {metadata.get('title', 'N/A')}
Author: {metadata.get('author', 'N/A')}
Language: {language}
Files changed: {files_str}
Branch: {metadata.get('head_branch', 'N/A')} -> {metadata.get('base_branch', 'main')}

## Retrieved Guidance
{state.get('retrieved_context', '')}

## Diff to Review
```diff
{diff_selection.content}
```

Write the review now."""

        response = invoke_llm(
            _llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)],
            agent="review_agent",
        )
        candidate: ReviewCandidate = {
            "id": f"initial-{len(state.get('candidates', []))}",
            "review": response.content,
            "strategy": "initial",
        }
        end_event = log_end(
            "review_agent",
            {
                "strategy": "initial",
                "language": language,
                "review_length": len(response.content),
                "included_files": diff_selection.included_files,
                "omitted_files": diff_selection.omitted_files,
            },
            (time.perf_counter() - started_at) * 1000,
        )
        return {
            "candidates": state.get("candidates", []) + [candidate],
            "trace": trace + [start_event, end_event],
        }
    except Exception as exc:
        error_event = log_error("review_agent", str(exc))
        return {
            "candidates": state.get("candidates", []),
            "trace": trace + [start_event, error_event],
        }
