"""
Selector agent chooses the best candidate from the scored candidate set.
"""
from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.graph.state import CandidateScore, SelectorAgentInput, SelectorAgentOutput
from backend.observability.logger import log_end, log_error, log_start, log_structured
from backend.utils.diff import prepare_diff_for_prompt
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


def _rerank(state: SelectorAgentInput) -> tuple[int, str]:
    candidates = state.get("candidates", [])
    score_lookup = _score_lookup(state.get("scores", []))
    diff_excerpt = prepare_diff_for_prompt(state.get("pr_diff", ""), max_chars=1000).content
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
{diff_excerpt}
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
        },
    )

    if not candidates:
        error_event = log_error("selector_agent", "No candidates")
        return {
            "selected_index": None,
            "selector_reason": "No candidates were produced by the pipeline.",
            "branch_improvement": None,
            "trace": trace + [start_event, error_event],
        }

    score_lookup = _score_lookup(scores)
    branch_taken = bool(state.get("branch_taken", False))
    try:
        if len(candidates) == 1:
            selected_index, rationale = 0, "Selected the only candidate returned by the pipeline."
        else:
            selected_index, rationale = _rerank(state)
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
    end_event = log_end(
        "selector_agent",
        {
            "selected_index": selected_index,
            "selected_strategy": candidates[selected_index]["strategy"],
            "selected_score": selected_score,
            "selector_reason": selector_reason,
            "branch_improvement": branch_improvement,
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "selected_index": selected_index,
        "selector_reason": selector_reason,
        "branch_improvement": branch_improvement,
        "trace": trace + [start_event, end_event],
    }
