"""
api/main.py — FastAPI application.

Response schema matches the frontend's AnalyzeResponse TypeScript interface:
  {
    score: number,
    strategies: Strategy[],
    selected_strategy: string,
    review: string,
    issues: Issue[],
    trace: TraceEntry[],
  }

Also keeps the previous /review/mock-prs and /health endpoints.
"""
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.graph.workflow import compiled_graph
from backend.graph.state import PRCriticState
from backend.mcp.github_mock import MOCK_PRS
from backend.api.issue_extractor import extract_issues

app = FastAPI(title="PR Critic", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models matching frontend TypeScript types ──────────────

class ReviewRequest(BaseModel):
    pr_url: str = Field(..., examples=["mock://pr/security-issue"])


class StrategyOut(BaseModel):
    id: str
    name: str
    score: float
    description: str


class IssueOut(BaseModel):
    severity: Literal["critical", "warning", "info"]
    file: str
    line: int
    message: str


class TraceEntryOut(BaseModel):
    agent: str
    level: Literal["INFO", "WARN", "ERROR", "DEBUG"]
    message: str
    timestamp: str


class ReviewResponse(BaseModel):
    """Matches the frontend AnalyzeResponse interface exactly."""
    score: float
    strategies: list[StrategyOut]
    selected_strategy: str
    review: str
    issues: list[IssueOut]
    trace: list[TraceEntryOut]


# ── Helpers ───────────────────────────────────────────────────────────────────

_STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "initial":           "Balanced review covering correctness, security, style, and maintainability.",
    "security_focus":    "Prioritizes authentication, injection, cryptographic weaknesses, and OWASP vulnerabilities.",
    "correctness_focus": "Focuses on logic errors, edge cases, null handling, and runtime correctness.",
    "typescript_idioms": "TypeScript/JavaScript idioms: type safety, hooks correctness, async patterns.",
    "python_idioms":     "Pythonic patterns, type annotations, PEP 8, and Python-specific anti-patterns.",
    "minimal_style":     "Pragmatic review: correctness first, then readability. Skips trivial style issues.",
}

_STRATEGY_DISPLAY_NAMES: dict[str, str] = {
    "initial":           "Balanced Review",
    "security_focus":    "Security-First Review",
    "correctness_focus": "Correctness Review",
    "typescript_idioms": "TypeScript/JS Review",
    "python_idioms":     "Python Best Practices",
    "minimal_style":     "Pragmatic Review",
}


def _normalize_trace(raw_trace: list[dict]) -> list[TraceEntryOut]:
    """
    Convert the internal trace format (ts, agent, event, data, duration_ms)
    to the frontend's TraceEntry format (agent, level, message, timestamp).
    """
    entries: list[TraceEntryOut] = []
    for ev in raw_trace:
        agent = ev.get("agent", "unknown")
        event_type = ev.get("event", "")
        data = ev.get("data", {})
        ts = ev.get("ts", datetime.now(timezone.utc).isoformat())

        # Determine level
        if event_type == "error":
            level: Literal["INFO", "WARN", "ERROR", "DEBUG"] = "ERROR"
        elif event_type == "routing_decision":
            level = "INFO"
        else:
            level = "INFO"

        # Check data for warning signals
        if isinstance(data, dict):
            if data.get("trigger_branch") is True:
                level = "WARN"
            if "error" in data:
                level = "ERROR"

        # Build human-readable message
        if event_type == "start":
            msg = f"Starting {agent}"
            if "diff_length" in data:
                msg += f" (diff: {data['diff_length']} chars)"
            if "language" in data:
                msg += f", language: {data['language']}"
        elif event_type == "end":
            msg_parts = []
            for key in ("score", "review_length", "context_length", "generated",
                        "selected_strategy", "mode", "language", "diff_length", "files_changed"):
                if key in data:
                    msg_parts.append(f"{key}={data[key]}")
            duration = ev.get("duration_ms")
            if duration:
                msg_parts.append(f"in {duration:.0f}ms")
            msg = f"{agent} completed" + (f": {', '.join(msg_parts)}" if msg_parts else "")
        elif event_type == "routing_decision":
            decision = data.get("decision", "?")
            reason = data.get("reason", "")
            level = "WARN" if decision == "branch" else "INFO"
            msg = f"Routing → {decision} ({reason})"
        elif event_type == "error":
            msg = f"Error: {data.get('error', 'unknown error')}"
        elif event_type == "fetch_complete":
            msg = (
                f"GitHub PR fetched: {data.get('files_changed', 0)} files, "
                f"language={data.get('language', '?')}, "
                f"diff={data.get('diff_length', 0)} chars"
            )
        else:
            msg = f"{agent} {event_type}"
            if data:
                snippet = str(data)[:120]
                msg += f": {snippet}"

        entries.append(TraceEntryOut(
            agent=agent,
            level=level,
            message=msg,
            timestamp=ts,
        ))
    return entries


def _candidates_to_strategies(candidates: list[dict]) -> list[StrategyOut]:
    """Convert internal ReviewCandidate dicts to StrategyOut objects."""
    out: list[StrategyOut] = []
    for c in candidates:
        strategy_id = c.get("strategy", "initial")
        out.append(StrategyOut(
            id=strategy_id,
            name=_STRATEGY_DISPLAY_NAMES.get(strategy_id, strategy_id.replace("_", " ").title()),
            score=round(c.get("score", 0.0), 2),
            description=_STRATEGY_DESCRIPTIONS.get(strategy_id, ""),
        ))
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/review", response_model=ReviewResponse)
async def review_pr(req: ReviewRequest):
    initial: PRCriticState = {
        "pr_url": req.pr_url,
        "pr_diff": "",
        "pr_metadata": {},
        "retrieved_context": "",
        "retrieval_sources": [],
        "candidates": [],
        "trigger_branch": False,
        "best_candidate": None,
        "selector_rationale": "",
        "trace": [],
    }

    try:
        result = compiled_graph.invoke(initial)
    except Exception as exc:
        logging.exception("Pipeline failed for %s", req.pr_url)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    best = result.get("best_candidate")
    if not best:
        raise HTTPException(status_code=500, detail="Pipeline produced no review candidate")

    # Build strategies list from all candidates (sorted by score desc)
    all_candidates = result.get("candidates", [])
    strategies = sorted(
        _candidates_to_strategies(all_candidates),
        key=lambda s: s.score,
        reverse=True,
    )

    # Extract structured issues from the best review
    files_changed = result.get("pr_metadata", {}).get("files_changed", [])
    raw_issues = extract_issues(best["review"], files_changed)
    issues_out = [
        IssueOut(
            severity=i["severity"],  # type: ignore[arg-type]
            file=i["file"],
            line=i["line"],
            message=i["message"],
        )
        for i in raw_issues
    ]

    # Normalize trace
    trace_out = _normalize_trace(result.get("trace", []))

    # Score: use best candidate score, scale 0-10 → int-ish float for UI
    score = round(best.get("score", 0.0), 1)

    return ReviewResponse(
        score=score,
        strategies=strategies,
        selected_strategy=best.get("strategy", "initial"),
        review=best["review"],
        issues=issues_out,
        trace=trace_out,
    )


@app.get("/review/mock-prs")
async def list_mock_prs():
    return {
        "mock_prs": [
            {"url": k, "title": v.title, "language": v.language}
            for k, v in MOCK_PRS.items()
        ]
    }


@app.get("/health")
async def health():
    from backend.config import settings
    return {
        "status": "ok",
        "version": "0.2.0",
        "github_token_set": bool(getattr(settings, "github_token", None)),
    }