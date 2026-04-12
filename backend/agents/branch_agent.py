"""
Branch Agent — generates alternative reviews using different strategies.
Called only when Critic scores below threshold.
Model: llama-3.1-8b-instant (need multiple completions quickly)
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
    temperature=0.6,   # higher temp = more diverse alternatives
    max_tokens=1024,
)

STRATEGIES = [
    {
        "name": "security_focus",
        "prompt": """You are a security-focused code reviewer.
Concentrate exclusively on: authentication flaws, injection vulnerabilities,
cryptographic weaknesses, hardcoded secrets, and insecure deserialization.
Reference OWASP guidelines. Structure: 1) Security Summary,
2) Vulnerabilities (CRITICAL/HIGH/MEDIUM/LOW), 3) Fixes, 4) Verdict.""",
    },
    {
        "name": "minimal_style",
        "prompt": """You are a pragmatic code reviewer who values simplicity.
Focus on correctness first, then readability, then Python idioms.
Skip trivial style issues. Flag only things that genuinely matter.
Structure: 1) What works well, 2) Real issues (must-fix vs nice-to-have),
3) Specific suggestions, 4) Verdict.""",
    },
]


def branch_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    diff = state.get("pr_diff", "")
    ctx = state.get("retrieved_context", "")
    meta = state.get("pr_metadata", {})
    existing = list(state.get("candidates", []))
    trace = list(state.get("trace", []))

    log_start("branch_agent", {
        "n_strategies": len(STRATEGIES),
        "existing_candidates": len(existing),
    })

    new_candidates: list[ReviewCandidate] = []

    for strategy in STRATEGIES[: settings.max_branch_alternatives]:
        try:
            human = f"""## PR Metadata
Title: {meta.get('title', 'N/A')} | Language: {meta.get('language', 'Python')}

## Coding Standards
{ctx}

## PR Diff
```diff
{diff}
```

Please review."""
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
            trace.append(log_error("branch_agent", f"strategy '{strategy['name']}' failed: {exc}"))

    ev = log_end("branch_agent", {
        "strategies": [s["name"] for s in STRATEGIES[: settings.max_branch_alternatives]],
        "generated": len(new_candidates),
    }, (time.perf_counter() - t0) * 1000)

    return {
        "candidates": existing + new_candidates,
        "trace": trace + [ev],
    }