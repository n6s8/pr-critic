"""
Branch agent responsible for creating genuine alternative review candidates
when the initial review underperforms the branch threshold.
"""
from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.graph.state import BranchAgentInput, BranchAgentOutput, CandidateScore, ReviewCandidate
from backend.observability.logger import log_end, log_error, log_start
from backend.utils.diff import prepare_diff_for_prompt
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.branch.groq_kwargs(api_key=settings.groq_api_key))

_BASE_RULES = """Analyze only the code in the provided diff.
Do not invent missing code or comment on files outside the diff.
Use the supplied programming language and keep the review grounded in the change itself."""

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
        },
    )

    initial_candidate = existing_candidates[0] if existing_candidates else None
    initial_score = existing_scores.get(0)
    diff_selection = prepare_diff_for_prompt(diff, max_chars=3500)
    files_str = ", ".join(metadata.get("files_changed", [])) or "unknown"
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

            prompt = f"""## PR Information
Title: {metadata.get('title', 'N/A')}
Language: {language}
Files changed: {files_str}

## Retrieved Guidance
{state.get('retrieved_context', '')}

## Prior Review To Improve
{initial_candidate['review'] if initial_candidate else 'No prior review available.'}

## Why Another Strategy Is Needed
{critique or 'The prior review did not meet the branch threshold.'}

## Diff To Review
```diff
{diff_selection.content}
```

Produce a materially different review using your assigned strategy."""

            response = invoke_llm(
                _llm,
                [SystemMessage(content=strategy["prompt"]), HumanMessage(content=prompt)],
                agent="branch_agent",
            )
            new_candidates.append({
                "id": f"{strategy['name']}-{offset}",
                "review": response.content,
                "strategy": strategy["name"],
            })
        except Exception as exc:
            trace.append(log_error("branch_agent", f"strategy '{strategy['name']}' failed: {exc}"))

    end_event = log_end(
        "branch_agent",
        {
            "language": language,
            "strategies_run": [strategy["name"] for strategy in strategies],
            "generated": len(new_candidates),
            "included_files": diff_selection.included_files,
            "omitted_files": diff_selection.omitted_files,
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "candidates": existing_candidates + new_candidates,
        "trace": trace + [start_event, end_event],
    }
