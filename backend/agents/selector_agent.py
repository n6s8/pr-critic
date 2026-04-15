"""
Selector Agent — picks the best review from all scored candidates.
Model: mixtral-8x7b (reasoning quality matters for final selection)
"""
import json
import re
import time

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import settings
from backend.graph.state import ReviewCandidate, SelectorAgentInput, SelectorAgentOutput
from backend.observability.logger import log_start, log_end, log_error, log_structured
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.selector.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """Select the best code review from the candidates below.
Consider overall quality, not just the numeric score.
Respond ONLY with valid JSON:
{"best_index": <int>, "rationale": "<one sentence>"}"""


def _rerank(candidates: list[ReviewCandidate], diff: str) -> tuple[int, str]:
    summaries = "\n\n".join(
        f"[{i}] strategy={c['strategy']} score={c['score']:.1f}\n{c['review'][:300]}..."
        for i, c in enumerate(candidates)
    )
    human = f"## Diff (first 400 chars)\n{diff[:400]}\n\n## Candidates\n{summaries}\n\nChoose best."
    try:
        resp = invoke_llm(
            _llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
            agent="selector_agent",
        )
        d = json.loads(resp.content.strip())
        idx = int(d.get("best_index", 0))
        if 0 <= idx < len(candidates):
            return idx, d.get("rationale", "")
    except Exception as exc:
        log_structured(
            "WARNING",
            "selector_rerank_fallback",
            agent="selector_agent",
            error_type=type(exc).__name__,
            error=str(exc),
        )
    # Fallback: highest score
    best = max(range(len(candidates)), key=lambda i: candidates[i]["score"])
    return best, "Fallback: highest numeric score"


def selector_agent(state: SelectorAgentInput) -> SelectorAgentOutput:
    t0 = time.perf_counter()
    candidates = state.get("candidates", [])
    log_start("selector_agent", {
        "n_candidates": len(candidates),
        "scores": [c["score"] for c in candidates],
    })

    if not candidates:
        ev = log_error("selector_agent", "No candidates")
        return {
            "best_candidate": None,
            "selector_rationale": "No candidates",
            "trace": state.get("trace", []) + [ev],
        }

    try:
        if len(candidates) == 1:
            idx, rationale = 0, "Single candidate"
        else:
            idx, rationale = _rerank(candidates, state.get("pr_diff", ""))

        best = candidates[idx]
        ev = log_end("selector_agent", {
            "selected_index": idx,
            "selected_strategy": best["strategy"],
            "selected_score": best["score"],
            "rationale": rationale,
            "all_scores": {c["strategy"]: c["score"] for c in candidates},
        }, (time.perf_counter() - t0) * 1000)

        return {
            "best_candidate": best,
            "selector_rationale": rationale,
            "trace": state.get("trace", []) + [ev],
        }

    except Exception as exc:
        best = max(candidates, key=lambda c: c["score"])
        ev = log_error("selector_agent", str(exc))
        return {
            "best_candidate": best,
            "selector_rationale": f"Error fallback: {exc}",
            "trace": state.get("trace", []) + [ev],
        }
