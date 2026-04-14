"""
Critic Agent — scores a review 0-10.
Model: mixtral-8x7b (stronger reasoning for evaluation)
Sets trigger_branch=True when score < threshold.
"""
import json
import re
import time
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import settings
from backend.graph.state import PRCriticState
from backend.observability.logger import log_start, log_end, log_error, log_routing
from backend.utils.resilience import invoke_llm

_llm = ChatGroq(
    model=settings.reasoning_model,
    api_key=settings.groq_api_key,
    temperature=0.1,
    max_tokens=512,
    timeout=settings.llm_timeout_seconds,
    max_retries=0,
)

_SYSTEM = """You are evaluating the quality of a code review.
Score it 0-10 across these dimensions:
- Usefulness (0-3): Are suggestions actionable and specific?
- Coverage (0-3): Are the important issues addressed?
- False positives (0-2): Does it avoid flagging non-issues?
- Clarity (0-2): Is it clearly written?

Respond ONLY with valid JSON, no extra text:
{"score": <float 0-10>, "rationale": "<one sentence>", "issues_identified": ["<issue1>"]}"""


def _parse(content: str) -> tuple[float, str, list[str]]:
    try:
        d = json.loads(content.strip())
        return float(d.get("score", 5.0)), d.get("rationale", ""), d.get("issues_identified", [])
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r'"score"\s*:\s*(\d+(?:\.\d+)?)', content)
    score = float(m.group(1)) if m else 5.0
    mr = re.search(r'"rationale"\s*:\s*"([^"]+)"', content)
    rationale = mr.group(1) if mr else ""
    return score, rationale, []


def critic_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    candidates = state.get("candidates", [])

    if not candidates:
        ev = log_error("critic_agent", "No candidates to evaluate")
        return {"trigger_branch": False, "trace": state.get("trace", []) + [ev]}

    idx = len(candidates) - 1
    candidate = candidates[idx]
    log_start("critic_agent", {
        "strategy": candidate["strategy"],
        "review_length": len(candidate["review"]),
    })

    try:
        human = f"""## PR Diff
```diff
{state.get('pr_diff', '')[:2000]}
```

## Review to Evaluate
{candidate['review']}

Score this review."""

        resp = invoke_llm(
            _llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
            agent="critic_agent",
        )
        score, rationale, issues = _parse(resp.content)
        score = max(0.0, min(10.0, score))

        updated = list(candidates)
        updated[idx] = {**candidate, "score": score, "score_rationale": rationale, "issues": issues}
        trigger = score < settings.branch_score_threshold

        ms = (time.perf_counter() - t0) * 1000
        ev = log_end("critic_agent", {
            "strategy": candidate["strategy"], "score": score,
            "rationale": rationale, "trigger_branch": trigger,
        }, ms)
        routing_ev = log_routing(
            "branch" if trigger else "select",
            f"score={score}, threshold={settings.branch_score_threshold}",
        )

        return {
            "candidates": updated,
            "trigger_branch": trigger,
            "trace": state.get("trace", []) + [ev, routing_ev],
        }

    except Exception as exc:
        ev = log_error("critic_agent", str(exc))
        return {
            "trigger_branch": False,
            "trace": state.get("trace", []) + [ev],
        }
