"""
FastAPI application — single POST /review endpoint.
Returns the best review + all candidates + full trace.
"""
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.graph.workflow import compiled_graph
from backend.graph.state import PRCriticState
from backend.mcp.github_mock import MOCK_PRS

app = FastAPI(title="PR Critic", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


class ReviewRequest(BaseModel):
    pr_url: str = Field(..., examples=["mock://pr/security-issue"])


class CandidateOut(BaseModel):
    strategy: str
    score: float
    score_rationale: str
    issues: list[str]
    review: str


class ReviewResponse(BaseModel):
    pr_url: str
    pr_title: str
    best_review: str
    best_strategy: str
    best_score: float
    selector_rationale: str
    triggered_branch: bool
    candidates: list[CandidateOut]
    trace: list[dict]
    processed_at: str


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
        logging.exception("Pipeline failed")
        raise HTTPException(500, f"Pipeline error: {exc}")

    best = result.get("best_candidate")
    if not best:
        raise HTTPException(500, "No review produced")

    return ReviewResponse(
        pr_url=req.pr_url,
        pr_title=result.get("pr_metadata", {}).get("title", "N/A"),
        best_review=best["review"],
        best_strategy=best["strategy"],
        best_score=best["score"],
        selector_rationale=result.get("selector_rationale", ""),
        triggered_branch=result.get("trigger_branch", False),
        candidates=[CandidateOut(**{k: c[k] for k in CandidateOut.model_fields})
                    for c in result.get("candidates", [])],
        trace=result.get("trace", []),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/review/mock-prs")
async def list_mock_prs():
    return {"mock_prs": [
        {"url": k, "title": v.title, "language": v.language}
        for k, v in MOCK_PRS.items()
    ]}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def frontend():
    return FileResponse("frontend/index.html")