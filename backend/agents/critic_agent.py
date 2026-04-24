"""
Critic agents score review candidates and decide whether the branch path is
necessary after the initial review.
"""
from __future__ import annotations

import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from backend.config import settings
from backend.graph.state import CandidateScore, CriticAgentInput, CriticAgentOutput
from backend.observability.logger import log_end, log_error, log_routing, log_start
from backend.utils.diff import prepare_diff_for_prompt
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(**settings.models.critic.groq_kwargs(api_key=settings.groq_api_key))

_SYSTEM = """You are evaluating the quality of a code review.

Score the review from 0 to 10 across:
- Usefulness
- Coverage
- False-positive control
- Clarity

Respond only with valid JSON:
{"score": 0.0, "rationale": "one sentence", "issues_identified": ["issue"]}"""


def _parse(content: str) -> tuple[float, str, list[str]]:
    try:
        data = json.loads(content.strip())
        return (
            float(data.get("score", 5.0)),
            str(data.get("rationale", "")),
            [str(issue) for issue in data.get("issues_identified", [])],
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    score_match = re.search(r'"score"\s*:\s*(\d+(?:\.\d+)?)', content)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]+)"', content)
    score = float(score_match.group(1)) if score_match else 5.0
    rationale = rationale_match.group(1) if rationale_match else ""
    return score, rationale, []


def _pending_indexes(candidate_count: int, scores: list[CandidateScore]) -> list[int]:
    scored_indexes = {score["candidate_index"] for score in scores}
    return [index for index in range(candidate_count) if index not in scored_indexes]


def _score_candidate(index: int, review: str, strategy: str, diff: str) -> CandidateScore:
    diff_excerpt = prepare_diff_for_prompt(diff, max_chars=2500).content
    prompt = f"""## Diff
```diff
{diff_excerpt}
```

## Review To Evaluate
{review}

Return the JSON score."""

    response = invoke_llm(
        _llm,
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)],
        agent="critic_agent",
    )
    score, rationale, issues_identified = _parse(response.content)
    return {
        "candidate_index": index,
        "strategy": strategy,
        "score": max(0.0, min(10.0, score)),
        "rationale": rationale,
        "issues_identified": issues_identified,
    }


def _run_critic(state: CriticAgentInput, *, set_branch_taken: bool) -> CriticAgentOutput:
    started_at = time.perf_counter()
    candidates = list(state.get("candidates", []))
    scores = list(state.get("scores", []))
    trace = list(state.get("trace", []))
    pending_indexes = _pending_indexes(len(candidates), scores)
    start_event = log_start(
        "critic_agent",
        {
            "candidate_count": len(candidates),
            "pending_indexes": pending_indexes,
        },
    )

    if not candidates:
        error_event = log_error("critic_agent", "No candidates to evaluate")
        result: CriticAgentOutput = {"scores": scores, "trace": trace + [start_event, error_event]}
        if set_branch_taken:
            result["branch_taken"] = False
        return result

    new_scores: list[CandidateScore] = []
    for index in pending_indexes:
        candidate = candidates[index]
        try:
            new_scores.append(
                _score_candidate(index, candidate["review"], candidate["strategy"], state.get("pr_diff", ""))
            )
        except Exception as exc:
            trace.append(log_error("critic_agent", f"Failed to score candidate {index}: {exc}"))
            new_scores.append({
                "candidate_index": index,
                "strategy": candidate["strategy"],
                "score": 0.0,
                "rationale": f"Critic failed: {exc}",
                "issues_identified": [],
            })

    updated_scores = sorted(scores + new_scores, key=lambda item: item["candidate_index"])
    branch_taken = state.get("branch_taken", False)
    routing_event = None
    if set_branch_taken:
        threshold = settings.thresholds.branch_score_threshold
        initial_score = next((score for score in updated_scores if score["candidate_index"] == 0), None)
        branch_taken = bool(initial_score and initial_score["score"] < threshold)
        routing_event = log_routing(
            "branch" if branch_taken else "select",
            f"score={initial_score['score'] if initial_score else 'n/a'}, threshold={threshold}",
        )

    end_event = log_end(
        "critic_agent",
        {
            "scored_indexes": [score["candidate_index"] for score in new_scores],
            "scores": {score["candidate_index"]: score["score"] for score in updated_scores},
            "branch_taken": branch_taken,
        },
        (time.perf_counter() - started_at) * 1000,
    )
    next_trace = trace + [start_event, end_event]
    if routing_event is not None:
        next_trace.append(routing_event)

    result: CriticAgentOutput = {"scores": updated_scores, "trace": next_trace}
    if set_branch_taken:
        result["branch_taken"] = branch_taken
    return result


def critic_agent(state: CriticAgentInput) -> CriticAgentOutput:
    return _run_critic(state, set_branch_taken=True)


def branch_critic_agent(state: CriticAgentInput) -> CriticAgentOutput:
    return _run_critic(state, set_branch_taken=False)
