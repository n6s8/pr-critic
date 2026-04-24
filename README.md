# PR Critic

PR Critic is a pull request review system with a FastAPI backend, a LangGraph workflow, a local retrieval layer, and a React dashboard. It analyzes a diff, produces one or more grounded review candidates, scores them independently, and returns the selected review together with the evidence used to make that decision.

## What The System Does

For each review request, the backend:

1. Fetches the raw diff and PR metadata
2. Retrieves language-relevant guidance from the local corpus
3. Generates an initial review candidate
4. Scores each candidate independently
5. Branches into alternate strategies only when the initial candidate underperforms
6. Selects the best candidate and returns the full result contract

The frontend renders only backend-owned data: PR metadata, real diff content, retrieval snippets, review candidates, the selected review, extracted issues, and a structured execution trace.

## What Makes This System Different

- Real evaluation: scenario runs are measured against `expected_issues` with precision, recall, F1, and false positives instead of synthetic score buckets.
- Multi-agent selection: the system keeps explicit candidate state, scores each candidate independently, and records `selector_reason` for the final decision.
- Explainable RAG: retrieval is visible as `{ source, snippet }` evidence instead of hidden prompt context.

## Backend Response Contract

The backend response is the source of truth for the frontend.

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
      "file": "src/components/ChatWindow.tsx",
      "line": 81,
      "message": "Example issue message."
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

- `fetch_agent`: loads the diff and metadata
- `rag_agent`: retrieves language-aware guidance from the local corpus
- `review_agent`: generates the initial review candidate
- `critic_agent`: scores each unscored candidate independently and decides whether branching is needed
- `branch_agent`: creates real alternative candidates with different review strategies
- `selector_agent`: chooses the best candidate and records `selector_reason`

### Backend

- Framework: FastAPI
- Orchestration: LangGraph
- Retrieval: local TF-IDF corpus
- Observability: structured trace events returned to the client

### Frontend

- Framework: React 18
- Build tool: Vite
- Language: TypeScript
- Contract rule: no parsing from logs and no synthetic diff or pipeline states

## Repository Layout

```text
backend/
  agents/           Review pipeline agents
  api/              FastAPI app and API helpers
  graph/            Workflow state and graph assembly
  mcp/              GitHub access and mock implementations
  observability/    Logging and trace helpers
  rag/              Retrieval components

data/               Retrieval corpus and local reference material
evaluation/         Scenarios and evaluation metrics
frontend/           React dashboard
scripts/            Developer utilities, including evaluation runner
tests/              Automated tests
```

## Requirements

- Python 3.11 or later
- Node.js 18 or later
- npm
- `GROQ_API_KEY` for live model execution

## Setup

### 1. Install backend dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

```env
GROQ_API_KEY=your_api_key
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

## Limitations

- The retrieval corpus is still small and local.
- GitHub webhook and GitHub App automation are not implemented.
- Very large PRs are chunked conservatively, not deeply optimized.

## Trade-offs

- The project uses simple local TF-IDF retrieval instead of a vector database to keep the system deterministic and low-overhead for a small corpus.
- Evaluation is local and scenario-based rather than human-labeled at scale, which keeps it repeatable but narrower than a full production benchmark.

## Notes

- The backend owns the response contract consumed by the frontend.
- Mock mode replaces model calls only; the evaluation metrics remain real.
- If retrieval is unavailable, the system returns an empty retrieval section instead of fabricated guidance.
