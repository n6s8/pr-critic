"""
agents/branch_agent.py — Language-aware Branch Agent.

Selects review strategies based on the detected language.
All prompts include anti-hallucination instructions.
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
    temperature=0.5,
    max_tokens=1200,
)

# Base rules prepended to every strategy prompt
_BASE_RULES = """CRITICAL: Analyze ONLY the code in the provided diff.
Do NOT invent or assume code that is not shown.
Do NOT comment on files not in the diff.
Use the programming language specified — do not default to Python."""

_ALL_STRATEGIES = [
    {
        "name": "security_focus",
        "languages": ["*"],
        "prompt": f"""{_BASE_RULES}

You are a security-focused code reviewer.
Focus EXCLUSIVELY on security issues visible in the diff:
authentication flaws, injection vulnerabilities, cryptographic weaknesses,
hardcoded secrets, insecure deserialization, XSS, CSRF, privilege escalation.
Reference OWASP guidelines. Do not comment on style or architecture.

Structure:
1) Security Summary (what security-relevant changes are in this diff)
2) Vulnerabilities Found (CRITICAL/HIGH/MEDIUM/LOW, with line references)
3) Recommended Fixes (concrete code or configuration changes)
4) Verdict: APPROVE / REQUEST_CHANGES""",
    },
    {
        "name": "correctness_focus",
        "languages": ["*"],
        "prompt": f"""{_BASE_RULES}

You are a correctness-focused code reviewer.
Focus on: logic errors, edge cases, null/undefined handling, error handling,
off-by-one errors, race conditions, and incorrect assumptions visible in the diff.
Do not comment on style or formatting.

Structure:
1) What the diff changes (brief, factual)
2) Correctness Issues (must-fix bugs and logic errors with line references)
3) Edge Cases Not Handled (visible from the diff only)
4) Verdict: APPROVE / REQUEST_CHANGES""",
    },
    {
        "name": "typescript_idioms",
        "languages": ["TypeScript", "JavaScript"],
        "prompt": f"""{_BASE_RULES}

You are a TypeScript/JavaScript expert reviewer.
Focus on: type safety, React hooks correctness, async/await patterns,
null safety (optional chaining, nullish coalescing), proper error handling,
and TypeScript-specific anti-patterns visible in the diff.

Structure:
1) TypeScript/JS Quality Summary
2) Type Safety Issues (missing types, any usage, unsafe casts)
3) React/Hooks Issues (if applicable — only if React is visible in diff)
4) Suggestions (idiomatic TypeScript/JS improvements)
5) Verdict: APPROVE / REQUEST_CHANGES""",
    },
    {
        "name": "python_idioms",
        "languages": ["Python"],
        "prompt": f"""{_BASE_RULES}

You are a Python expert reviewer.
Focus on: Pythonic patterns, type annotations, exception handling,
PEP 8 compliance, performance pitfalls (N+1, list vs generator),
and Python-specific anti-patterns visible in the diff.

Structure:
1) Python Quality Summary
2) Non-Pythonic Patterns (with idiomatic alternatives)
3) Type Annotation Issues
4) Performance Concerns (only if visible in the diff)
5) Verdict: APPROVE / REQUEST_CHANGES""",
    },
]


def _strategies_for_language(language: str) -> list[dict]:
    """
    Select the two most relevant strategies for the detected language.
    Always includes security_focus. Adds language-specific strategy when available,
    otherwise falls back to correctness_focus.
    """
    lang_specific = next(
        (s for s in _ALL_STRATEGIES
         if language in s["languages"] and s["languages"] != ["*"]),
        None,
    )
    fallback  = next(s for s in _ALL_STRATEGIES if s["name"] == "correctness_focus")
    security  = next(s for s in _ALL_STRATEGIES if s["name"] == "security_focus")

    selected = [security, lang_specific or fallback]
    seen: set[str] = set()
    result = []
    for s in selected:
        if s["name"] not in seen:
            seen.add(s["name"])
            result.append(s)
    return result


def _safe_diff(diff: str, max_chars: int = 3500) -> str:
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + "\n\n... [diff truncated for branch review]"


def branch_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    diff     = state.get("pr_diff", "")
    ctx      = state.get("retrieved_context", "")
    meta     = state.get("pr_metadata", {})
    lang     = meta.get("language", "Unknown")
    existing = list(state.get("candidates", []))
    trace    = list(state.get("trace", []))

    strategies = _strategies_for_language(lang)[: settings.max_branch_alternatives]
    log_start("branch_agent", {
        "language": lang,
        "n_strategies": len(strategies),
        "strategy_names": [s["name"] for s in strategies],
        "existing_candidates": len(existing),
    })

    new_candidates: list[ReviewCandidate] = []
    files_str = ", ".join(meta.get("files_changed", [])) or "unknown"

    for strategy in strategies:
        try:
            human = f"""## PR Information
Title: {meta.get('title', 'N/A')}
Language: {lang}
Files: {files_str}

## Coding Standards
{ctx}

## Diff to Review
IMPORTANT: Review ONLY the following diff.
```diff
{_safe_diff(diff)}
```

Please review using your assigned strategy."""
            resp = _llm.invoke([
                SystemMessage(content=strategy["prompt"]),
                HumanMessage(content=human),
            ])
            new_candidates.append({
                "review": resp.content,
                "strategy": strategy["name"],
                "score": 0.0,
                "score_rationale": "",
                "issues": [],
            })
        except Exception as exc:
            trace.append(log_error("branch_agent",
                                   f"strategy '{strategy['name']}' failed: {exc}"))

    ev = log_end("branch_agent", {
        "strategies_run": [s["name"] for s in strategies],
        "generated": len(new_candidates),
        "language": lang,
    }, (time.perf_counter() - t0) * 1000)

    return {
        "candidates": existing + new_candidates,
        "trace": trace + [ev],
    }