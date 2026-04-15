"""
agents/review_agent.py — Review Agent.

Anti-hallucination improvements:
  - System prompt instructs: analyze ONLY the diff provided
  - System prompt instructs: do NOT assume missing code
  - Language passed explicitly — no Python assumption
  - Temperature lowered to 0.2
"""
import time

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import settings
from backend.graph.state import ReviewAgentInput, ReviewAgentOutput, ReviewCandidate
from backend.observability.logger import log_start, log_end, log_error
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.review.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """You are a senior software engineer performing a precise code review.

CRITICAL RULES — you MUST follow these:
1. Analyze ONLY the code visible in the provided diff. Lines starting with "+" are additions.
2. Do NOT assume, infer, or comment on code that is NOT in the diff.
3. Do NOT invent issues that are not directly visible in the provided changes.
4. Use the EXACT programming language specified — do not assume Python for non-Python code.
5. Reference specific line numbers or code snippets from the diff for every issue you raise.

Review structure (follow exactly):
## Summary
One or two sentences describing what this PR does based on the diff.

## Issues Found
List each issue as:
- [SEVERITY] [FILE:LINE if visible] Description
  Where SEVERITY is one of: CRITICAL, MAJOR, MINOR

## Suggestions
Concrete, specific improvements with code examples where helpful.

## Verdict
One of: APPROVE / REQUEST_CHANGES / COMMENT
Include a one-sentence justification."""


def _safe_diff(diff: str, max_chars: int = 4000) -> str:
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + f"\n\n... [diff truncated at {max_chars} chars for review]"


def review_agent(state: ReviewAgentInput) -> ReviewAgentOutput:
    t0 = time.perf_counter()
    diff = state.get("pr_diff", "")
    ctx  = state.get("retrieved_context", "")
    meta = state.get("pr_metadata", {})
    lang = meta.get("language", "Unknown")

    log_start("review_agent", {
        "diff_length": len(diff),
        "language": lang,
        "context_sources": state.get("retrieval_sources", []),
    })

    if not diff.strip() or diff.strip().startswith("# ERROR:"):
        review_text = (
            "No diff content available for review.\n\n"
            + (diff if diff.strip().startswith("# ERROR:") else "")
        )
        candidate: ReviewCandidate = {
            "review": review_text,
            "strategy": "initial",
            "score": 0.0,
            "score_rationale": "No diff available",
            "issues": [],
        }
        ev = log_end("review_agent", {"strategy": "initial", "empty": True},
                     (time.perf_counter() - t0) * 1000)
        return {
            "candidates": state.get("candidates", []) + [candidate],
            "trace": state.get("trace", []) + [ev],
        }

    try:
        files_str = ", ".join(meta.get("files_changed", [])) or "unknown"
        human = f"""## PR Information
Title: {meta.get('title', 'N/A')}
Author: {meta.get('author', 'N/A')}
Language: {lang}
Files changed: {files_str}
Branch: {meta.get('head_branch', 'N/A')} → {meta.get('base_branch', 'main')}

## Coding Standards for {lang}
{ctx}

## Diff to Review
IMPORTANT: Review ONLY the following diff. Do not comment on code outside this diff.
```diff
{_safe_diff(diff)}
```

Please review this PR following the rules in your system prompt."""

        resp = invoke_llm(
            _llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
            agent="review_agent",
        )
        candidate = {
            "review": resp.content,
            "strategy": "initial",
            "score": 0.0,
            "score_rationale": "",
            "issues": [],
        }
        ev = log_end("review_agent", {
            "strategy": "initial",
            "language": lang,
            "review_length": len(resp.content),
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
