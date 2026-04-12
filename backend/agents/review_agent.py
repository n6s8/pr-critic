"""
Review Agent — generates the initial code review.
Model: llama-3.1-8b-instant (fast generation)
"""
import time
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import settings
from backend.graph.state import PRCriticState, ReviewCandidate
from backend.observability.logger import log_start, log_end, log_error

_llm = ChatGroq(
    model=settings.generation_model,
    api_key=settings.groq_api_key,
    temperature=0.3,
    max_tokens=1024,
)

_SYSTEM = """You are a senior software engineer performing a code review.
Review the PR diff using the provided coding standards as reference.
Focus on: correctness, security, style, maintainability, and test coverage.

Structure your review exactly as:
1. Summary (1-2 sentences)
2. Issues Found (each with severity: CRITICAL / MAJOR / MINOR and line reference)
3. Suggestions (concrete, specific improvements)
4. Verdict: APPROVE / REQUEST_CHANGES / COMMENT

Be concise. Reference line numbers. Do not invent issues not visible in the diff."""


def review_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    diff = state.get("pr_diff", "")
    ctx = state.get("retrieved_context", "")
    meta = state.get("pr_metadata", {})

    log_start("review_agent", {
        "diff_length": len(diff),
        "context_sources": state.get("retrieval_sources", []),
    })

    # Empty diff shortcut
    if not diff.strip():
        candidate: ReviewCandidate = {
            "review": "No diff content. Cannot review.",
            "strategy": "initial",
            "score": 0.0,
            "score_rationale": "Empty diff",
            "issues": [],
        }
        ev = log_end("review_agent", {"strategy": "initial", "empty": True},
                     (time.perf_counter() - t0) * 1000)
        return {
            "candidates": state.get("candidates", []) + [candidate],
            "trace": state.get("trace", []) + [ev],
        }

    try:
        human = f"""## PR Metadata
Title: {meta.get('title', 'N/A')}
Author: {meta.get('author', 'N/A')}
Files: {', '.join(meta.get('files_changed', []))}
Language: {meta.get('language', 'Python')}

## Coding Standards Reference
{ctx}

## PR Diff
```diff
{diff}
```

Please review this PR."""

        resp = _llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
        candidate = {
            "review": resp.content,
            "strategy": "initial",
            "score": 0.0,
            "score_rationale": "",
            "issues": [],
        }
        ev = log_end("review_agent", {
            "strategy": "initial", "review_length": len(resp.content),
        }, (time.perf_counter() - t0) * 1000)
        return {
            "candidates": state.get("candidates", []) + [candidate],
            "trace": state.get("trace", []) + [ev],
        }

    except Exception as exc:
        ev = log_error("review_agent", str(exc))
        return {
            "candidates": state.get("candidates", []),
            "trace": state.get("trace", []) + [ev],
        }