# PR Critic

PR Critic is a pull request review system built around a FastAPI backend, a LangGraph workflow, a local TF-IDF retrieval layer, and a React dashboard. It analyzes a diff, generates review candidates, scores them independently, and returns the selected review together with retrieval evidence, extracted issues, and a structured execution trace.

## What The System Actually Does

For each review request, the backend:

1. Fetches raw diff and PR metadata through a local MCP GitHub tool boundary, with mock, evaluation, GitHub, and raw-diff sources behind that interface
2. Collects best-effort repository-aware signals for GitHub PRs:
   - changed file types
   - basic lint findings from `flake8` and/or `eslint` when those tools are available
3. Retrieves up to two compact guidance snippets from the local corpus
4. Applies smart diff filtering before the first LLM call:
   - ranks files by backend relevance, risky paths and patterns, and change size
   - deprioritizes docs and config
   - selects only the top review chunks before prompting the model
5. Builds a review plan that chooses focus areas such as security, correctness, style, or design
6. Generates one initial review candidate from the filtered diff packet plus compact repository signals, or a deterministic `large_pr_partial` candidate when the diff is too large for credible exhaustive review
7. Scores candidates independently
8. Branches into alternate strategies only when the initial candidate is weak, the request is not rate-limited, the PR is not in large-PR mode, and enough token budget remains
9. Runs a false-positive guard that rejects issues without changed-line evidence
10. Synthesizes grounded findings across candidates and returns the full contract for the frontend

The frontend renders backend-owned data only: metadata, diff, retrieval hits, candidates, extracted issues, and trace. It does not invent streaming progress, synthesize review text, or simulate missing steps.

## Execution Characteristics

- Smart diff filtering: the normal review path does not send the full diff to the model. It sends a bounded packet assembled from the highest-priority chunks.
- Token-aware prompting: the initial review path keeps the filtered diff itself around 900 tokens and keeps the overall review prompt in a bounded range, typically around 1000-1500 tokens, with an upper guard below the broader prompt ceiling.
- Compact RAG: retrieval uses `top_k=2` and short snippets only.
- Repository-aware signals: for GitHub PRs the backend performs a best-effort checkout, summarizes file types, and runs basic lint when `flake8` or `eslint` are available in the runtime.
- Large PR mode: if the raw diff exceeds the large-PR threshold, branching and review-generation LLM calls are skipped; the system returns an explicit `large_pr_partial` candidate with partial-coverage limitations.
- Adaptive execution: branching is conditional, not automatic.
- Honest degraded mode: GitHub fetch failures return errors, and LLM rate limits return explicit degraded/fallback behavior instead of fake reviews.

## What Makes This System Credible

- Issue-level evaluation: evaluation compares structured expected issues to structured detected issues and reports precision, recall, F1, and false positives.
- Real MCP boundary: GitHub PR metadata and diff access are exposed as MCP tools (`get_pull_request`, `get_pull_request_diff`) and consumed by the fetch agent through an async MCP client wrapper.
- Real multi-agent state: fetch, planner, RAG, review, critic, branch, false-positive guard, synthesis, and selector are separate graph stages with explicit shared artifacts.
- Explainable evidence: every surviving issue includes file, line, changed-line snippet, and source id when retrieval support is available.
- Production observability: structured JSON logs, agent latency, estimated token/cost metrics, MCP tool latency, retrieval stats, `/metrics`, `/health`, and `/feedback`.

## Backend Response Contract

```json
{
  "language": "TypeScript",
  "files_changed": ["src/components/ChatWindow.tsx"],
  "diff_size": 3268,
  "pr_metadata": {
    "title": "Sanitize profile rendering",
    "author": "octocat",
    "base_branch": "main",
    "head_branch": "fix/profile-xss",
    "language": "TypeScript",
    "files_changed": ["src/components/ChatWindow.tsx"],
    "pr_url": "https://github.com/org/repo/pull/123"
  },
  "diff": "diff --git a/src/components/ChatWindow.tsx ...",
  "retrieval": [
    {
      "source": "react_security",
      "section": "XSS",
      "snippet": "Avoid dangerouslySetInnerHTML unless the HTML is sanitized first.",
      "relevance": 0.92
    }
  ],
  "candidates": [
    {
      "index": 0,
      "id": "initial-0",
      "strategy": "initial",
      "review": "## Summary\n...",
      "score": 8.5,
      "score_rationale": "Strong coverage of the visible risk.",
      "critic_issues": ["xss", "sanitization"]
    }
  ],
  "selected_index": 0,
  "selected_review": {
    "index": 0,
    "id": "initial-0",
    "strategy": "initial",
    "review": "## Summary\n...",
    "score": 8.5,
    "score_rationale": "Strong coverage of the visible risk.",
    "critic_issues": ["xss", "sanitization"]
  },
  "score": 8.5,
  "selector_reason": "Selected the only candidate returned by the pipeline.",
  "branch_taken": false,
  "branch_improvement": null,
  "issues": [
    {
      "severity": "warning",
      "issue_type": "xss",
      "file": "src/components/ChatWindow.tsx",
      "line": 81,
      "message": "Unsanitized HTML rendering is visible in the changed component.",
      "code_snippet": "return <div dangerouslySetInnerHTML={{ __html: bio }} />",
      "source_id": "react_security:XSS"
    }
  ],
  "trace": [
    {
      "agent": "fetch_agent",
      "event": "end",
      "status": "completed",
      "timestamp": "2026-04-13T15:54:06.892849+00:00",
      "duration_ms": 23.4,
      "data": {
        "language": "TypeScript",
        "diff_length": 3268
      }
    }
  ]
}
```

## Architecture

### Review Pipeline

- `fetch_agent`: loads diff and metadata through the MCP client and enables large-PR mode when needed
- `fetch_agent`: for GitHub PRs, also collects repository-aware file-type and lint signals
- `planner_agent`: decides the review focus and expected issue types from the diff and safety flags
- `rag_agent`: retrieves up to two compact language-aware guidance snippets
- `review_agent`: builds the filtered diff packet, incorporates compact repository signals, generates the initial review for normal PRs, emits a deterministic `large_pr_partial` candidate for huge PRs, and emits an explicit fallback if the LLM is unavailable
- `critic_initial`: scores the initial candidate and decides whether branching is justified
- `branch_agent`: creates bounded alternate candidates with different strategies only when branching is allowed
- `critic_branch`: scores branch candidates only
- `false_positive_guard_agent`: removes issues that are not tied to changed lines or are weak generic suggestions
- `synthesis_agent`: builds a final grounded decision artifact across candidates
- `selector_agent`: chooses the best candidate, synthesizes grounded issues across candidates, and records `selector_reason`

### Backend

- Framework: FastAPI
- Orchestration: LangGraph
- Retrieval: local TF-IDF corpus
- Caching: in-memory fetch, RAG, and initial-review caches
- Observability: structured trace events returned to the client

### Frontend

- Framework: React 18
- Build tool: Vite
- Language: TypeScript
- Contract rule: no parsing from logs and no synthetic pipeline states

## Repository Layout

```text
backend/
  agents/           Review pipeline agents
  api/              FastAPI app and API helpers
  graph/            Workflow state and graph assembly
  mcp/              MCP client, models, and mock-compatible PR data provider
  mcp_server/       MCP GitHub tool server boundary
  observability/    Logging, trace helpers, and metrics registry
  rag/              Retrieval components
  security.py       Input validation, prompt-injection detection, PII masking, API-key auth

data/               Retrieval corpus and local reference material
evaluation/         Scenarios and issue-level evaluation metrics
frontend/           React dashboard
scripts/            Developer utilities, including evaluation runner
tests/              Automated tests
```

## Requirements

- Python 3.11 or later
- Node.js 18 or later
- npm
- `GROQ_API_KEY` for live model execution
- Optional: `GITHUB_TOKEN` for higher GitHub API limits

## Setup

### 1. Install backend dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

```env
GROQ_API_KEY=your_api_key
GITHUB_TOKEN=optional_github_token
MCP_TRANSPORT=inprocess
PR_CRITIC_API_KEY=optional_api_key_for_nonlocal_deployments
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

## Running The Project

### Start the backend

```bash
uvicorn backend.api.main:app --reload --port 8000
```

### Start the frontend

```bash
cd frontend
npm run dev
```

## API Endpoints

- `POST /review`: runs the full review pipeline for a diff source
- `GET /review/mock-prs`: lists built-in mock PRs for local testing
- `GET /health`: returns service health and runtime metadata
- `GET /metrics`: returns in-memory latency, token, cost, retrieval, feedback, and MCP metrics
- `POST /feedback`: records user rating/comment feedback for review quality assessment

## Local Development Workflow

### Run tests

```bash
pytest -v
```

### Run evaluation in mock mode

```bash
python scripts/run_evaluation.py --mock
```

### Run evaluation in live mode

```bash
python scripts/run_evaluation.py --delay 1.0
```

### Run real-world evaluation against public GitHub PRs

```bash
python scripts/run_evaluation.py --mock --real-world
```

## Evaluation Position

- Evaluation is issue-level, not keyword-based.
- The metrics are computed on structured local scenarios, not on human-labeled production PRs.
- Mock mode keeps the evaluation logic real but swaps live LLM calls for deterministic stand-ins.
- Current mock score after the capstone hardening pass: 20/20 successful, average precision 1.0, recall 1.0, F1 1.0, zero false positives.
- CI includes a live evaluation sanity job only when a real `GROQ_API_KEY` secret is configured.
- A separate real-world dataset of public GitHub PRs is available in [evaluation/real_world_cases.json](evaluation/real_world_cases.json) and documented in [REAL_WORLD_EVALUATION.md](REAL_WORLD_EVALUATION.md).

## Production Considerations

- Token budget enforcement keeps the main review prompt bounded and predictable instead of allowing arbitrary diff growth.
- Smart diff filtering reduces prompt size before every LLM call, including critic and selector reasoning passes.
- Adaptive branching prevents multi-pass expansion when the initial score is already acceptable, when the PR is too large, or when the token budget is already tight.
- Graceful degradation keeps the pipeline alive under rate limits and upstream fetch failures and makes the degraded state explicit in both trace and UI.
- The API validates review sources, rejects malformed URLs, masks PII/secrets in logs and prompts, detects prompt-injection text in diffs, and supports API-key protection.
- Caching is intentionally conservative:
  - GitHub fetches, retrieval context, initial review results, and repository-aware signals are cached in memory
  - the cache layer now has an abstraction boundary that is ready for a distributed backend such as Redis, but Redis is not implemented yet

## Deployment Notes

- Backend:
  - `GROQ_API_KEY` is required for live review generation
  - `GITHUB_TOKEN` is optional but recommended for higher GitHub API limits and more stable real-world evaluation
  - `CACHE_BACKEND` currently supports `memory`; `redis` is reserved for a future distributed backend
  - `REPO_SIGNAL_TIMEOUT_SECONDS` controls the best-effort checkout/lint budget for repository-aware signals
- Frontend:
  - set `VITE_API_URL` to the deployed backend base URL
- Scaling considerations:
  - the current cache and rate-limit implementation is process-local
  - horizontally scaled deployments would need shared cache/rate-limit storage and a coordinated repository checkout strategy

## Known Limitations

- The system does not review the full repository; it reviews a filtered subset of the diff.
- Repository-aware signals are best-effort and depend on runtime access to `git`, `flake8`, and/or `eslint`.
- Very large PRs are handled in partial-analysis mode, with branching disabled for stability.
- The retrieval corpus is still small and local.
- Caches are in-memory only.
- Horizontal scaling is not implemented.
- GitHub webhook / GitHub App automation is not implemented.
- Evaluation is still narrower than a human benchmark on real reviewer decisions.

## Notes

- The backend owns the response contract consumed by the frontend.
- If retrieval is unavailable, the system returns an empty retrieval section instead of fabricated guidance.
- If the model is rate-limited, the system degrades explicitly instead of pretending a full review was produced.

## System Positioning

This project is not a demo-style single prompt with a decorative trace, and it is not yet a fully productionized PR review platform. It is a realistic AI engineering system: explicit orchestration, bounded prompting, compact retrieval, repository-aware signals, issue-level evaluation, honest degraded behavior, and a frontend that reflects real backend state instead of inventing it.
