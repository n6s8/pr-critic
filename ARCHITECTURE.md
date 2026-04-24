# PR Critic - Architecture Blueprint

## System Overview

PR Critic is a pull request review system with a FastAPI backend, a LangGraph workflow, a local TF-IDF retriever, and a React dashboard.

Request flow:

1. `POST /review` accepts a diff source
2. `fetch_agent` loads PR metadata and the raw diff
3. `rag_agent` retrieves local language-aware guidance
4. `review_agent` generates the initial candidate
5. `critic_agent` scores each unscored candidate independently
6. If the initial score is below threshold, `branch_agent` creates real alternatives
7. `critic_branch` scores only the new branch candidates
8. `selector_agent` chooses the best candidate and records `selector_reason`
9. The API returns the full structured contract for the frontend

The architecture is intentionally modest:

- Retrieval is local and deterministic, not vector-database based
- The graph runs per request with in-memory state
- Rate limiting and caches are in-memory
- The frontend renders completed backend responses, not simulated or streamed states

## Components

### Frontend

- React 18 + TypeScript + Vite
- Renders backend-owned metadata, diff content, retrieval snippets, review candidates, issues, and trace
- Does not parse logs or invent missing data

### Backend API

- FastAPI
- Endpoints:
  - `POST /review`
  - `GET /review/mock-prs`
  - `GET /health`
- Normalizes trace events and returns the response contract consumed by the frontend

### Orchestration

- LangGraph
- Shared state: `PRCriticState`
- Nodes:
  - `fetch`
  - `rag`
  - `review`
  - `critic`
  - `branch`
  - `critic_branch`
  - `selector`

### Retrieval

- Strategy: TF-IDF over a local corpus
- Sources include OWASP, PEP 8, TypeScript best practices, and React security notes
- If retrieval is unavailable, the system returns empty retrieval evidence instead of fabricated guidance

## Agent Design

| Agent | Input | Output | Responsibility |
|---|---|---|---|
| `fetch_agent` | `pr_url` | `pr_diff`, `pr_metadata` | Load diff and metadata from mock data, evaluation scenarios, GitHub, or raw input |
| `rag_agent` | `pr_diff`, `language` | `retrieved_context`, `retrieval_sources`, `retrieval_hits` | Retrieve language-aware review guidance |
| `review_agent` | diff, metadata, retrieval context | initial candidate | Generate the first grounded review candidate |
| `critic_agent` | diff, candidates, scores | updated `scores`, optional `branch_taken` | Score each unscored candidate independently |
| `branch_agent` | diff, metadata, retrieval context, prior score | additional candidates | Generate real alternative candidates with different review strategies |
| `selector_agent` | candidates, scores, diff | `selected_index`, `selector_reason`, `branch_improvement` | Choose the best candidate from the scored candidate set |

Branching rules:

- The initial critic pass sets `branch_taken = true` only if the initial candidate score is below threshold
- The branch critic pass scores only pending branch candidates
- The branch critic pass never overwrites `branch_taken`
- `branch_improvement` is computed as `selected_score - initial_score` when branching occurred

## Shared State

```python
pr_url: str
pr_diff: str
pr_metadata: dict
retrieved_context: str
retrieval_sources: list[str]
retrieval_hits: list[dict]
candidates: list[dict]
scores: list[dict]
branch_taken: bool
branch_improvement: float | None
selected_index: int | None
selector_reason: str
trace: list[dict]
request_context: dict
```

Key invariants:

- `candidates[index]` is the candidate reviewed by `scores[candidate_index=index]`
- `selected_index` always points into `candidates`
- `branch_taken` is a routing fact, not a scratch flag
- `branch_improvement` is only populated when branching occurred and both baseline and selected scores exist

## API Contract

```json
{
  "language": "Python",
  "files_changed": ["auth/utils.py"],
  "diff_size": 412,
  "pr_metadata": {
    "title": "Security fix",
    "author": "octocat",
    "base_branch": "main",
    "head_branch": "fix/auth",
    "language": "Python",
    "files_changed": ["auth/utils.py"],
    "pr_url": "https://github.com/org/repo/pull/42"
  },
  "diff": "diff --git a/auth/utils.py ...",
  "retrieval": [
    {
      "source": "owasp_top10",
      "section": "A03 Injection",
      "snippet": "Use parameterized SQL queries.",
      "relevance": 0.94
    }
  ],
  "candidates": [
    {
      "index": 0,
      "id": "initial-0",
      "strategy": "initial",
      "review": "## Summary\n...",
      "score": 8.5,
      "score_rationale": "Strong coverage of the visible risks.",
      "critic_issues": ["sql injection", "md5"]
    }
  ],
  "selected_index": 0,
  "selected_review": {
    "index": 0,
    "id": "initial-0",
    "strategy": "initial",
    "review": "## Summary\n...",
    "score": 8.5,
    "score_rationale": "Strong coverage of the visible risks.",
    "critic_issues": ["sql injection", "md5"]
  },
  "score": 8.5,
  "selector_reason": "Selected the only candidate returned by the pipeline.",
  "branch_taken": false,
  "branch_improvement": null,
  "issues": [
    {
      "severity": "critical",
      "file": "auth/utils.py",
      "line": 4,
      "message": "Use parameterized queries."
    }
  ],
  "trace": [
    {
      "agent": "fetch_agent",
      "event": "end",
      "status": "completed",
      "timestamp": "2026-04-13T15:54:06.892849+00:00",
      "duration_ms": 23.0,
      "data": {
        "language": "Python",
        "diff_length": 412
      }
    }
  ]
}
```

## Evaluation Design

Per-run metrics:

- `precision`
- `recall`
- `f1`
- `false_positives`
- `review_score`
- `triggered_branch`
- `branch_improvement`
- `selected_strategy`

Summary metrics:

- `avg_precision`
- `avg_recall`
- `avg_f1`
- `total_false_positives`
- `branching_rate_pct`
- `avg_branch_improvement`
- `avg_latency_ms`

Mock mode keeps the evaluation logic real. It only swaps out live LLM calls for deterministic local behavior so the pipeline can be exercised without external credentials.

## What Makes This System Different

- Real evaluation against scenario expectations
- Multi-agent selection with explicit candidate state
- Explainable retrieval returned to the frontend as structured evidence

## Limitations

- The retrieval corpus is still small and local
- No GitHub webhook or GitHub App integration
- Large PR handling is basic diff chunking, not deep prioritization

## Trade-offs

- Local TF-IDF retrieval is simpler and more deterministic than a vector database for a small corpus
- Scenario-based local evaluation is easier to repeat than human labeling, but narrower than full human review benchmarking
