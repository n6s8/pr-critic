"""
FastAPI application for the PR Critic backend.

The backend owns the review contract consumed by the frontend. The API returns
real metadata, the raw diff, scored candidates, structured retrieval evidence,
and structured trace events.
"""
from __future__ import annotations

import math
import json
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from backend.api.issue_extractor import extract_issues
from backend.config import settings
from backend.errors import PRCriticError
from backend.graph.state import build_initial_state, build_request_context
from backend.mcp.github_mock import MOCK_PRS
from backend.observability.context import request_context_scope
from backend.observability.logger import configure_logging, get_logger, log_structured
from backend.observability.metrics import record_feedback, record_request, snapshot_metrics
from backend.security import require_api_key, validate_review_source
from backend.services.review_runtime import run_review_pipeline_async

configure_logging()

app = FastAPI(title="PR Critic", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_api_log = get_logger("pr_critic.api")
_rate_limit_state: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = Lock()

_TRACE_CONTEXT_KEYS = {
    "request_id",
    "route_path",
    "path",
    "method",
    "client_id",
    "submitted_at",
    "execution_mode",
}


class ReviewRequest(BaseModel):
    pr_url: str = Field(..., examples=["https://github.com/org/repo/pull/123"])

    @field_validator("pr_url")
    @classmethod
    def validate_pr_url(cls, value: str) -> str:
        return validate_review_source(value)


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
    review_id: str | None = Field(default=None, max_length=128)


class IssueOut(BaseModel):
    severity: Literal["critical", "warning", "info"]
    issue_type: str
    file: str
    line: int
    message: str
    code_snippet: str = ""
    source_id: str = "diff"


class RetrievalHitOut(BaseModel):
    source: str
    section: str
    snippet: str
    relevance: float


class CandidateOut(BaseModel):
    index: int
    id: str
    strategy: str
    review: str
    score: float
    score_rationale: str
    critic_issues: list[str]


class PRMetadataOut(BaseModel):
    title: str
    author: str
    base_branch: str
    head_branch: str
    language: str
    files_changed: list[str]
    pr_url: str


class TraceEntryOut(BaseModel):
    agent: str
    event: str
    status: Literal["started", "completed", "warning", "error", "routing"]
    timestamp: str
    duration_ms: float | None = None
    data: dict[str, Any]


class ReviewResponse(BaseModel):
    language: str
    files_changed: list[str]
    diff_size: int
    pr_metadata: PRMetadataOut
    diff: str
    retrieval: list[RetrievalHitOut]
    candidates: list[CandidateOut]
    selected_index: int
    selected_review: CandidateOut
    selector_reason: str
    branch_taken: bool
    branch_improvement: float | None = None
    score: float
    issues: list[IssueOut]
    trace: list[TraceEntryOut]


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


def _jsonable(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


def _trace_status(event_type: str, data: dict[str, Any]) -> Literal["started", "completed", "warning", "error", "routing"]:
    if event_type == "start":
        return "started"
    if event_type == "routing_decision":
        return "routing"
    if event_type == "error" or "error" in data:
        return "error"
    if (
        data.get("fallback_used")
        or data.get("degraded")
        or data.get("rate_limited")
        or data.get("large_pr_mode")
        or str(data.get("branch_skipped_reason", "")) in {"rate_limited", "large_pr_mode", "review_unavailable", "token_budget"}
    ):
        return "warning"
    if data.get("branch_taken") is True:
        return "warning"
    return "completed"


def _normalize_trace(raw_trace: list[dict]) -> list[TraceEntryOut]:
    entries: list[TraceEntryOut] = []
    for event in raw_trace:
        data = event.get("data", {})
        cleaned_data = {
            key: value
            for key, value in data.items()
            if key not in _TRACE_CONTEXT_KEYS
        } if isinstance(data, dict) else {}
        entries.append(
            TraceEntryOut(
                agent=event.get("agent", "unknown"),
                event=event.get("event", "unknown"),
                status=_trace_status(event.get("event", "unknown"), cleaned_data),
                timestamp=event.get("ts", datetime.now(timezone.utc).isoformat()),
                duration_ms=event.get("duration_ms"),
                data=cleaned_data,
            )
        )
    return entries


def _candidate_score_map(result: dict) -> dict[int, dict]:
    return {
        score["candidate_index"]: score
        for score in result.get("scores", [])
    }


def _build_candidates(result: dict) -> list[CandidateOut]:
    score_map = _candidate_score_map(result)
    candidates: list[CandidateOut] = []
    for index, candidate in enumerate(result.get("candidates", [])):
        score = score_map.get(index, {})
        candidates.append(
            CandidateOut(
                index=index,
                id=candidate.get("id", f"candidate-{index}"),
                strategy=candidate.get("strategy", "unknown"),
                review=candidate.get("review", ""),
                score=round(float(score.get("score", 0.0)), 2),
                score_rationale=str(score.get("rationale", "")),
                critic_issues=[str(item) for item in score.get("issues_identified", [])],
            )
        )
    return candidates


def _issues_from_review(review_text: str, files_changed: list[str]) -> list[IssueOut]:
    return [
        IssueOut(
            severity=issue["severity"],  # type: ignore[arg-type]
            issue_type=issue["issue_type"],
            file=issue["file"],
            line=issue["line"],
            message=issue["message"],
            code_snippet="",
            source_id="diff",
        )
        for issue in extract_issues(review_text, files_changed)
    ]


def _issues_from_grounded(raw_issues: list[dict]) -> list[IssueOut]:
    return [
        IssueOut(
            severity=issue.get("severity", "info"),  # type: ignore[arg-type]
            issue_type=str(issue.get("issue_type", "unknown")),
            file=str(issue.get("file", "unknown")),
            line=int(issue.get("line") or 0),
            message=str(issue.get("message", "")),
            code_snippet=str(issue.get("code_snippet", "")),
            source_id=str(issue.get("source_id", "diff")),
        )
        for issue in raw_issues
    ]


def _trace_has_rate_limit(raw_trace: list[dict]) -> bool:
    for event in raw_trace:
        data = event.get("data", {})
        text = f"{event.get('event', '')} {event.get('agent', '')} {data}".lower()
        if "rate limit" in text or "429" in text or "too many requests" in text or data.get("reason") == "llm_rate_limited":
            return True
    return False


def _trace_retry_after_seconds(raw_trace: list[dict]) -> float | None:
    retry_after: float | None = None
    for event in raw_trace:
        data = event.get("data", {})
        value = data.get("retry_after_seconds") if isinstance(data, dict) else None
        if value is None:
            continue
        try:
            retry_after = max(retry_after or 0.0, float(value))
        except (TypeError, ValueError):
            continue
    return retry_after


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
            log_structured("WARNING", "rate_limit_exceeded")
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

        if request.url.path != "/health" and not require_api_key(dict(request.headers)):
            log_structured("WARNING", "api_key_rejected")
            response = JSONResponse(
                status_code=401,
                content=_error_payload(
                    401,
                    "unauthorized",
                    "Missing or invalid API key.",
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
            log_structured("ERROR", "request_failed_uncaught", duration_ms=duration_ms)
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_structured("INFO", "request_completed", status_code=response.status_code, duration_ms=duration_ms)
        response.headers["X-Request-ID"] = request_id
        return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    error_code = "http_error"
    if isinstance(exc.detail, str):
        message = exc.detail
    elif isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or exc.detail.get("detail") or "Request failed")
        error_code = str(exc.detail.get("code") or error_code)
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
        content=_error_payload(exc.status_code, error_code, message, request_id, exc.detail),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    errors = _jsonable(exc.errors())
    log_structured(
        "WARNING",
        "validation_error",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        errors=errors,
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            422,
            "validation_error",
            "Invalid request payload.",
            request_id,
            errors,
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
    record_request()
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
    except PRCriticError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        ) from exc
    except Exception as exc:
        _api_log.exception(
            "Pipeline failed for %s",
            req.pr_url,
            extra={"extra": {"request_id": getattr(request.state, "request_id", "unknown"), "pr_url": req.pr_url}},
        )
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    trace_events = result.get("trace", [])
    candidates = _build_candidates(result)
    if not candidates:
        is_rate_limited = _trace_has_rate_limit(trace_events)
        retry_after_seconds = _trace_retry_after_seconds(trace_events)
        message = (
            "LLM unavailable due to rate limit. Please retry shortly."
            if is_rate_limited
            else "No review candidates were produced. The review service is temporarily unavailable."
        )
        code = "llm_rate_limited" if is_rate_limited else "review_unavailable"
        headers = (
            {"Retry-After": str(max(1, math.ceil(retry_after_seconds)))}
            if retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": message,
                "code": code,
                "details": {"retry_after_seconds": retry_after_seconds} if retry_after_seconds is not None else {},
            },
            headers=headers,
        )

    selected_index = result.get("selected_index")
    if selected_index is None or not (0 <= selected_index < len(candidates)):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Review candidates were produced, but the pipeline could not select a final review.",
                "code": "selection_unavailable",
            },
        )

    selected_review = candidates[selected_index]
    pr_metadata = result.get("pr_metadata", {})
    files_changed = list(pr_metadata.get("files_changed", []))
    grounded = result.get("grounded_issues", [])
    grounded_by_candidate = result.get("candidate_grounded_issues", {})
    if not grounded and isinstance(grounded_by_candidate, dict):
        grounded = grounded_by_candidate.get(str(selected_index), [])
    issues = _issues_from_grounded(grounded) if grounded else _issues_from_review(selected_review.review, files_changed)

    return ReviewResponse(
        language=str(pr_metadata.get("language", "Unknown")),
        files_changed=files_changed,
        diff_size=len(result.get("pr_diff", "")),
        pr_metadata=PRMetadataOut(
            title=str(pr_metadata.get("title", "")),
            author=str(pr_metadata.get("author", "")),
            base_branch=str(pr_metadata.get("base_branch", "main")),
            head_branch=str(pr_metadata.get("head_branch", "")),
            language=str(pr_metadata.get("language", "Unknown")),
            files_changed=files_changed,
            pr_url=str(pr_metadata.get("pr_url", req.pr_url)),
        ),
        diff=result.get("pr_diff", ""),
        retrieval=[
            RetrievalHitOut(
                source=hit.get("source", "unknown"),
                section=hit.get("section", "general"),
                snippet=hit.get("snippet", ""),
                relevance=float(hit.get("relevance", 0.0)),
            )
            for hit in result.get("retrieval_hits", [])
        ],
        candidates=candidates,
        selected_index=selected_index,
        selected_review=selected_review,
        selector_reason=result.get("selector_reason", ""),
        branch_taken=bool(result.get("branch_taken", False)),
        branch_improvement=result.get("branch_improvement"),
        score=round(selected_review.score, 2),
        issues=issues,
        trace=_normalize_trace(trace_events),
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
        "version": "0.3.0",
        "environment": settings.app_env,
        "github_token_set": bool(getattr(settings, "github_token", None)),
        "mcp_transport": settings.mcp_transport,
        "api_auth_enabled": bool(settings.api_key),
        "cors_allowed_origins": settings.api.cors_allowed_origins,
    }


@app.get("/metrics")
async def metrics():
    return snapshot_metrics()


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    return {
        "status": "recorded",
        "feedback": record_feedback(req.rating, req.comment, req.review_id),
    }
