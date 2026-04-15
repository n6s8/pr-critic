"""
FastAPI application for the PR Critic backend.

Success responses keep the same contract used by the frontend:
  {
    score: number,
    strategies: Strategy[],
    selected_strategy: string,
    review: string,
    issues: Issue[],
    trace: TraceEntry[],
  }
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.issue_extractor import extract_issues
from backend.config import settings
from backend.graph.state import build_initial_state, build_request_context
from backend.mcp.github_mock import MOCK_PRS
from backend.observability.context import request_context_scope
from backend.observability.logger import configure_logging, get_logger, log_structured
from backend.services.review_runtime import run_review_pipeline_async

configure_logging()

app = FastAPI(title="PR Critic", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_api_log = get_logger("pr_critic.api")
_rate_limit_state: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = Lock()


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
    score: float
    strategies: list[StrategyOut]
    selected_strategy: str
    review: str
    issues: list[IssueOut]
    trace: list[TraceEntryOut]


_STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "initial": "Balanced review covering correctness, security, style, and maintainability.",
    "security_focus": "Prioritizes authentication, injection, cryptographic weaknesses, and OWASP vulnerabilities.",
    "correctness_focus": "Focuses on logic errors, edge cases, null handling, and runtime correctness.",
    "typescript_idioms": "TypeScript/JavaScript idioms: type safety, hooks correctness, async patterns.",
    "python_idioms": "Pythonic patterns, type annotations, PEP 8, and Python-specific anti-patterns.",
    "minimal_style": "Pragmatic review: correctness first, then readability. Skips trivial style issues.",
}

_STRATEGY_DISPLAY_NAMES: dict[str, str] = {
    "initial": "Balanced Review",
    "security_focus": "Security-First Review",
    "correctness_focus": "Correctness Review",
    "typescript_idioms": "TypeScript/JS Review",
    "python_idioms": "Python Best Practices",
    "minimal_style": "Pragmatic Review",
}


def _normalize_trace(raw_trace: list[dict]) -> list[TraceEntryOut]:
    """Convert internal trace events to the frontend trace shape."""
    entries: list[TraceEntryOut] = []
    for event in raw_trace:
        agent = event.get("agent", "unknown")
        event_type = event.get("event", "")
        data = event.get("data", {})
        ts = event.get("ts", datetime.now(timezone.utc).isoformat())

        if event_type == "error":
            level: Literal["INFO", "WARN", "ERROR", "DEBUG"] = "ERROR"
        elif event_type == "routing_decision":
            level = "INFO"
        else:
            level = "INFO"

        if isinstance(data, dict):
            if data.get("trigger_branch") is True:
                level = "WARN"
            if "error" in data:
                level = "ERROR"

        if event_type == "start":
            message = f"Starting {agent}"
            if "diff_length" in data:
                message += f" (diff: {data['diff_length']} chars)"
            if "language" in data:
                message += f", language: {data['language']}"
        elif event_type == "end":
            message_parts = []
            for key in (
                "score",
                "review_length",
                "context_length",
                "generated",
                "selected_strategy",
                "mode",
                "language",
                "diff_length",
                "files_changed",
                "cache_hit",
            ):
                if key in data:
                    message_parts.append(f"{key}={data[key]}")
            duration = event.get("duration_ms")
            if duration:
                message_parts.append(f"in {duration:.0f}ms")
            message = f"{agent} completed" + (f": {', '.join(message_parts)}" if message_parts else "")
        elif event_type == "routing_decision":
            decision = data.get("decision", "?")
            reason = data.get("reason", "")
            level = "WARN" if decision == "branch" else "INFO"
            message = f"Routing -> {decision} ({reason})"
        elif event_type == "error":
            message = f"Error: {data.get('error', 'unknown error')}"
        elif event_type == "fetch_complete":
            message = (
                f"GitHub PR fetched: {data.get('files_changed', 0)} files, "
                f"language={data.get('language', '?')}, "
                f"diff={data.get('diff_length', 0)} chars"
            )
        else:
            message = f"{agent} {event_type}"
            if data:
                message += f": {str(data)[:120]}"

        entries.append(
            TraceEntryOut(
                agent=agent,
                level=level,
                message=message,
                timestamp=ts,
            )
        )
    return entries


def _candidates_to_strategies(candidates: list[dict]) -> list[StrategyOut]:
    out: list[StrategyOut] = []
    for candidate in candidates:
        strategy_id = candidate.get("strategy", "initial")
        out.append(
            StrategyOut(
                id=strategy_id,
                name=_STRATEGY_DISPLAY_NAMES.get(strategy_id, strategy_id.replace("_", " ").title()),
                score=round(candidate.get("score", 0.0), 2),
                description=_STRATEGY_DESCRIPTIONS.get(strategy_id, ""),
            )
        )
    return out


def _error_payload(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: object | None = None,
) -> dict:
    payload = {
        "detail": message,
        "error": {
            "code": code,
            "message": message,
            "status_code": status_code,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _client_id(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limit_exceeded(client_id: str) -> bool:
    now = time.monotonic()
    rate_limit = settings.rate_limit
    with _rate_limit_lock:
        bucket = _rate_limit_state[client_id]
        while bucket and now - bucket[0] > rate_limit.window_seconds:
            bucket.popleft()
        if len(bucket) >= rate_limit.requests:
            return True
        bucket.append(now)
        return False


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    client_id = _client_id(request)

    with request_context_scope(
        request_id=request_id,
        route_path=request.url.path,
        path=request.url.path,
        method=request.method,
        client_id=client_id,
    ):
        if request.url.path != "/health" and _rate_limit_exceeded(client_id):
            log_structured(
                "WARNING",
                "rate_limit_exceeded",
            )
            response = JSONResponse(
                status_code=429,
                content=_error_payload(
                    429,
                    "rate_limited",
                    "Too many requests. Please retry shortly.",
                    request_id,
                ),
            )
            response.headers["X-Request-ID"] = request_id
            return response

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            log_structured(
                "ERROR",
                "request_failed_uncaught",
                duration_ms=duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_structured(
            "INFO",
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    if isinstance(exc.detail, str):
        message = exc.detail
    elif isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or exc.detail.get("detail") or "Request failed")
    else:
        message = "Request failed"

    log_structured(
        "ERROR" if exc.status_code >= 500 else "WARNING",
        "http_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.status_code, "http_error", message, request_id, exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    log_structured(
        "WARNING",
        "validation_error",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            422,
            "validation_error",
            "Invalid request payload.",
            request_id,
            exc.errors(),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    _api_log.exception(
        "Unhandled exception",
        extra={
            "extra": {
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        },
    )
    return JSONResponse(
        status_code=500,
        content=_error_payload(500, "internal_error", "Internal server error.", request_id),
    )


@app.post("/review", response_model=ReviewResponse)
async def review_pr(req: ReviewRequest, request: Request):
    initial = build_initial_state(
        req.pr_url,
        request_context=build_request_context(
            getattr(request.state, "request_id", str(uuid.uuid4())),
            execution_mode="async_threadpool",
            route_path=request.url.path,
        ),
    )

    try:
        result = await run_review_pipeline_async(initial)
    except Exception as exc:
        _api_log.exception(
            "Pipeline failed for %s",
            req.pr_url,
            extra={
                "extra": {
                    "request_id": getattr(request.state, "request_id", "unknown"),
                    "pr_url": req.pr_url,
                }
            },
        )
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    best = result.get("best_candidate")
    if not best:
        raise HTTPException(status_code=500, detail="Pipeline produced no review candidate")

    all_candidates = result.get("candidates", [])
    strategies = sorted(
        _candidates_to_strategies(all_candidates),
        key=lambda strategy: strategy.score,
        reverse=True,
    )

    files_changed = result.get("pr_metadata", {}).get("files_changed", [])
    raw_issues = extract_issues(best["review"], files_changed)
    issues_out = [
        IssueOut(
            severity=issue["severity"],  # type: ignore[arg-type]
            file=issue["file"],
            line=issue["line"],
            message=issue["message"],
        )
        for issue in raw_issues
    ]

    trace_out = _normalize_trace(result.get("trace", []))
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
            {"url": key, "title": value.title, "language": value.language}
            for key, value in MOCK_PRS.items()
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "github_token_set": bool(getattr(settings, "github_token", None)),
    }
